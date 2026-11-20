"""Command-line interface for the Unpack developer tool."""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

from . import __version__
from .config import DEFAULT_SERVER_URL, DEFAULT_TIMEOUT_S, get_config_path, resolve_repo_config
from .git_info import GitError, detect_default_branch, get_repo_root
from .hook import (
    build_push_payload,
    get_hook_status,
    install_hook,
    run_pre_push_hook,
    uninstall_hook,
)
from .mock_server import run_mock_server
from .agy_session import find_agy_session
from .session_finder import find_gemini_session, resolve_gemini_project_ids
from .transport import IngestError, format_ingest_result, send_ingest_payload


def _mask_token(token: str | None) -> str:
    if not token:
        return "(none)"
    if len(token) <= 8:
        return "***"
    return f"{token[:4]}...{token[-4:]}"


def _cmd_install(args: argparse.Namespace) -> int:
    try:
        repo_root = get_repo_root()
    except GitError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    default_branch = args.default_branch or detect_default_branch(repo_root)
    hook_path, backup_path = install_hook(
        repo_root,
        server_url=args.server,
        token=args.token,
        default_branch=default_branch,
        timeout_s=args.timeout,
    )
    print(f"Installed Unpack pre-push hook at {hook_path}")
    if backup_path is not None:
        print(f"Preserved existing hook at {backup_path} (will run before Unpack)")
    print(f"Saved config for {repo_root} in {get_config_path()} (server={args.server})")
    return 0


def _cmd_uninstall(args: argparse.Namespace) -> int:
    try:
        repo_root = get_repo_root()
    except GitError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    removed_hook, restored_backup, removed_cfg = uninstall_hook(
        repo_root, remove_config=args.remove_config
    )
    if removed_hook:
        print("Removed Unpack pre-push hook.")
    else:
        print("No Unpack-managed pre-push hook found.")
    if restored_backup:
        print("Restored original pre-push hook.")
    if removed_cfg:
        print(f"Removed repo entry from {get_config_path()}.")
    return 0


def _cmd_push(args: argparse.Namespace) -> int:
    try:
        repo_root = get_repo_root()
    except GitError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    cfg = resolve_repo_config(
        repo_root,
        server_override=args.server,
        token_override=args.token,
        default_branch_override=args.default_branch,
        timeout_override=args.timeout,
    )
    session_override = Path(args.session).expanduser() if args.session else None

    try:
        payload, selected_session = build_push_payload(
            repo_root,
            base_sha=args.base,
            head_sha=args.head,
            default_branch_override=cfg.default_branch,
            session_path=session_override,
            agent=args.agent,
            hook_name="manual",
        )
    except Exception as exc:
        print(f"Error building payload: {exc}", file=sys.stderr)
        return 1

    if args.dry_run is not None:
        serialized = json.dumps(payload, indent=2, ensure_ascii=False)
        gzip_len = len(gzip.compress(serialized.encode("utf-8")))
        if args.dry_run == "-":
            print(serialized)
        else:
            out_path = Path(args.dry_run).expanduser()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(serialized + "\n", encoding="utf-8")
            sess_desc = (
                f"{selected_session} ({len(payload['session']['lines'])} lines)"
                if selected_session and payload["session"]
                else "none"
            )
            print(f"Wrote dry-run payload to {out_path}")
            base_short = payload["base_sha"][:7]
            head_short = payload["head_sha"][:7]
            print(
                f"Summary: branch={payload['branch']} {base_short}..{head_short} "
                f"commits={len(payload['commits'])} files={len(payload['changed_files'])} "
                f"session={sess_desc}"
            )
            print(
                f"Size: {len(serialized.encode('utf-8')):,} bytes JSON "
                f"({gzip_len:,} bytes gzip) | redactions={payload['redactions']}"
            )
        return 0

    try:
        resp = send_ingest_payload(
            cfg.server_url,
            payload,
            token=cfg.token,
            timeout_s=cfg.timeout_s,
        )
    except IngestError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(
        format_ingest_result(
            resp,
            branch=payload["branch"],
            head_sha=payload["head_sha"],
            redactions=payload["redactions"],
            has_session=payload["session"] is not None,
        )
    )
    return 0


def _cmd_status(_args: argparse.Namespace) -> int:
    try:
        repo_root = get_repo_root()
    except GitError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    cfg = resolve_repo_config(repo_root)
    hook_info = get_hook_status(repo_root)
    project_ids = resolve_gemini_project_ids(repo_root)
    newest_session = find_gemini_session(repo_root)

    print(f"Unpack CLI v{__version__}")
    print(f"  Repo root:       {repo_root}")
    print(f"  Config file:     {get_config_path()}")
    print(f"  Server URL:      {cfg.server_url}")
    print(f"  Token:           {_mask_token(cfg.token)}")
    print(f"  Default branch:  {cfg.default_branch or detect_default_branch(repo_root)}")
    print(f"  Timeout:         {cfg.timeout_s:.1f}s")

    if hook_info["installed"]:
        chain_note = (
            f" (chaining {hook_info['chained_backup'].name})"
            if hook_info["chained_backup"]
            else ""
        )
        print(f"  pre-push hook:   installed at {hook_info['hook_path']}{chain_note}")
    elif hook_info["has_other_hook"]:
        print(
            f"  pre-push hook:   not installed (non-Unpack hook exists at {hook_info['hook_path']})"
        )
    else:
        print("  pre-push hook:   not installed")

    newest_agy = find_agy_session(repo_root)
    print(f"  Antigravity:     {newest_agy or '(none found)'}")
    print(f"  Gemini ID:       {project_ids[0] if project_ids else '(none)'}")
    print(f"  Latest Gemini:   {newest_session or '(none found)'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="unpack", description="Unpack developer CLI")
    parser.add_argument("--version", action="version", version=f"unpack {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # install
    install_p = subparsers.add_parser(
        "install", help="Install git pre-push hook and save repo config"
    )
    install_p.add_argument(
        "--server", default=DEFAULT_SERVER_URL, help="Unpack server base URL"
    )
    install_p.add_argument(
        "--token", default=None, help="Repository ingest token (optional for localhost)"
    )
    install_p.add_argument(
        "--default-branch", default=None, help="Override default branch (auto-detected if omitted)"
    )
    install_p.add_argument(
        "--timeout", type=float, default=DEFAULT_TIMEOUT_S, help="HTTP timeout in seconds"
    )

    # uninstall
    uninstall_p = subparsers.add_parser(
        "uninstall", help="Remove Unpack pre-push hook and restore any original hook"
    )
    uninstall_p.add_argument(
        "--remove-config",
        action="store_true",
        help="Also remove this repo's entry from ~/.config/unpack/config.json",
    )

    # hook (internal, called by .git/hooks/pre-push)
    hook_p = subparsers.add_parser("hook", help="Run pre-push hook action (reads refs on stdin)")
    hook_p.add_argument("--server", default=None, help="Override server URL")
    hook_p.add_argument("--token", default=None, help="Override ingest token")
    hook_p.add_argument("git_args", nargs="*", help="Arguments passed by git pre-push")

    # push (manual trigger / dry-run)
    push_p = subparsers.add_parser(
        "push", help="Build and send (or dry-run inspect) the ingest payload for HEAD"
    )
    push_p.add_argument(
        "--dry-run",
        nargs="?",
        const=".unpack-dry-run.json",
        default=None,
        metavar="PATH",
        help="Write redacted payload to PATH (default .unpack-dry-run.json, or '-' for stdout)",
    )
    push_p.add_argument(
        "--session",
        default=None,
        metavar="PATH",
        help="Explicit JSONL session file to include instead of auto-discovery",
    )
    push_p.add_argument(
        "--agent",
        default="antigravity-cli",
        help="Agent label for session payload (default: antigravity-cli; gemini-cli for Gemini CLI)",
    )
    push_p.add_argument("--base", default=None, help="Explicit base commit SHA")
    push_p.add_argument("--head", default=None, help="Explicit head commit SHA")
    push_p.add_argument("--server", default=None, help="Override Unpack server URL")
    push_p.add_argument("--token", default=None, help="Override repository ingest token")
    push_p.add_argument("--default-branch", default=None, help="Override default branch")
    push_p.add_argument("--timeout", type=float, default=None, help="HTTP timeout in seconds")

    # status
    subparsers.add_parser("status", help="Show Unpack hook, config, and session status")

    # mock-server
    mock_p = subparsers.add_parser(
        "mock-server", help="Start a local mock /ingest server for end-to-end testing"
    )
    mock_p.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    mock_p.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    mock_p.add_argument(
        "--out-dir",
        default=".unpack-mock-payloads",
        help="Directory to write received payload JSON files",
    )

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "install":
        sys.exit(_cmd_install(args))
    elif args.command == "uninstall":
        sys.exit(_cmd_uninstall(args))
    elif args.command == "hook":
        sys.exit(run_pre_push_hook(server_override=args.server, token_override=args.token))
    elif args.command == "push":
        sys.exit(_cmd_push(args))
    elif args.command == "status":
        sys.exit(_cmd_status(args))
    elif args.command == "mock-server":
        out_dir = Path(args.out_dir).expanduser() if args.out_dir else None
        run_mock_server(host=args.host, port=args.port, out_dir=out_dir)


if __name__ == "__main__":
    main()
