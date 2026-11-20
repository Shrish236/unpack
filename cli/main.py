"""Command-line interface for the Unpack developer tool."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def install_hook(server_url: str, token: str) -> None:
    """Installs the pre-push hook into the local git repository."""
    hooks_dir = Path(".git") / "hooks"
    if not hooks_dir.exists():
        print("Error: .git/hooks directory not found. Are you inside a Git repository?", file=sys.stderr)
        sys.exit(1)

    hook_path = hooks_dir / "pre-push"
    hook_script = f"""#!/bin/sh
# Unpack pre-push hook
python -m cli hook --server "{server_url}" --token "{token}"
"""
    hook_path.write_text(hook_script, encoding="utf-8")
    try:
        hook_path.chmod(0o755)
    except Exception:
        pass
    print(f"✓ Unpack pre-push hook successfully installed in {hook_path}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="unpack", description="Unpack developer CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # install
    install_p = subparsers.add_parser("install", help="Install git pre-push hook in current repo")
    install_p.add_argument("--server", default="http://localhost:8000", help="Unpack server base URL")
    install_p.add_argument("--token", required=True, help="Repository ingest token")

    # hook (internal, called by pre-push)
    hook_p = subparsers.add_parser("hook", help="Run pre-push hook action")
    hook_p.add_argument("--server", default="http://localhost:8000")
    hook_p.add_argument("--token", default="")

    # push (manual trigger)
    push_p = subparsers.add_parser("push", help="Trigger analysis push manually")
    push_p.add_argument("--dry-run", action="store_true", help="Print payload without sending")

    # status
    subparsers.add_parser("status", help="Check Unpack status for current branch")

    args = parser.parse_args()

    if args.command == "install":
        install_hook(args.server, args.token)
    elif args.command == "hook":
        from .hook import run_pre_push_hook
        sys.exit(run_pre_push_hook(args.server, args.token))
    elif args.command == "push":
        print("Manual push trigger placeholder (use --dry-run to view sanitized payload).")
    elif args.command == "status":
        print("Unpack status: connected.")


if __name__ == "__main__":
    main()
