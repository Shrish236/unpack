"""Pre-push git hook management and push-context pipeline for Unpack."""

from __future__ import annotations

import shlex
import sys
from pathlib import Path
from typing import Any

from .config import (
    DEFAULT_TIMEOUT_S,
    remove_repo_config,
    resolve_repo_config,
    save_repo_config,
)
from .git_info import (
    ZERO_SHA,
    get_changed_files,
    get_commits,
    get_current_branch,
    get_head_sha,
    get_hooks_dir,
    get_oldest_commit_parent_time,
    get_repo_ref,
    get_repo_root,
    get_unified_diff,
    resolve_base_sha,
)
from .agy_session import find_agy_session, get_agy_cli_version
from .secrets import SecretScanner
from .session_finder import (
    find_gemini_session,
    get_gemini_cli_version,
    load_and_trim_session,
)
from .transport import build_ingest_payload, format_ingest_result, send_ingest_payload

HOOK_MARKER = "# Unpack pre-push hook (managed by unpack-cli)"
BACKUP_HOOK_NAME = "pre-push.unpack-orig"


def get_hook_status(repo_root: Path) -> dict[str, Any]:
    """Inspect pre-push hook installation and chaining state."""
    hooks_dir = get_hooks_dir(repo_root)
    hook_path = hooks_dir / "pre-push"
    backup_path = hooks_dir / BACKUP_HOOK_NAME

    installed = False
    if hook_path.exists():
        try:
            installed = HOOK_MARKER in hook_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            installed = False

    return {
        "hook_path": hook_path,
        "installed": installed,
        "has_other_hook": hook_path.exists() and not installed,
        "chained_backup": backup_path if backup_path.exists() else None,
    }


def install_hook(
    repo_root: Path,
    *,
    server_url: str,
    token: str | None = None,
    default_branch: str | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    python_executable: str | None = None,
) -> tuple[Path, Path | None]:
    """Save repo config and install a chaining git pre-push hook.

    Returns (hook_path, backup_path_or_none).
    """
    save_repo_config(
        repo_root,
        server_url=server_url,
        token=token,
        default_branch=default_branch,
        timeout_s=timeout_s,
    )

    hooks_dir = get_hooks_dir(repo_root)
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_path = hooks_dir / "pre-push"
    backup_path = hooks_dir / BACKUP_HOOK_NAME

    chained_backup: Path | None = backup_path if backup_path.exists() else None
    if hook_path.exists():
        existing = hook_path.read_text(encoding="utf-8", errors="replace")
        if HOOK_MARKER not in existing:
            if not backup_path.exists():
                hook_path.rename(backup_path)
                chained_backup = backup_path

    py_bin = shlex.quote(python_executable or sys.executable)
    pkg_parent = shlex.quote(str(Path(__file__).resolve().parent.parent))
    backup_quoted = shlex.quote(str(backup_path))

    script = f"""#!/bin/sh
{HOOK_MARKER}
UNPACK_STDIN="$(mktemp "${{TMPDIR:-/tmp}}/unpack-pre-push.XXXXXX")"
trap 'rm -f "$UNPACK_STDIN"' EXIT
cat > "$UNPACK_STDIN"

if [ -x {backup_quoted} ]; then
  {backup_quoted} "$@" < "$UNPACK_STDIN"
  UNPACK_ORIG_EXIT=$?
  if [ "$UNPACK_ORIG_EXIT" -ne 0 ]; then
    exit "$UNPACK_ORIG_EXIT"
  fi
fi

PYTHONPATH={pkg_parent}"${{PYTHONPATH:+:$PYTHONPATH}}" \\
  {py_bin} -m cli hook "$@" < "$UNPACK_STDIN" || true
exit 0
"""
    hook_path.write_text(script, encoding="utf-8")
    hook_path.chmod(0o755)
    return hook_path, chained_backup


def uninstall_hook(
    repo_root: Path, *, remove_config: bool = False
) -> tuple[bool, bool, bool]:
    """Remove Unpack pre-push hook and restore any backed-up hook.

    Returns (removed_hook, restored_backup, removed_config).
    """
    hooks_dir = get_hooks_dir(repo_root)
    hook_path = hooks_dir / "pre-push"
    backup_path = hooks_dir / BACKUP_HOOK_NAME

    removed_hook = False
    restored_backup = False

    if hook_path.exists():
        content = hook_path.read_text(encoding="utf-8", errors="replace")
        if HOOK_MARKER in content:
            hook_path.unlink()
            removed_hook = True
            if backup_path.exists():
                backup_path.rename(hook_path)
                restored_backup = True

    removed_cfg = remove_repo_config(repo_root) if remove_config else False
    return removed_hook, restored_backup, removed_cfg


def parse_pre_push_refs(stdin_text: str) -> list[tuple[str, str, str, str]]:
    """Parse git pre-push stdin lines, skipping branch deletes and tag pushes."""
    refs: list[tuple[str, str, str, str]] = []
    for raw_line in stdin_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        local_ref, local_sha, remote_ref, remote_sha = parts[:4]
        if local_sha == ZERO_SHA:
            continue
        if local_ref.startswith("refs/tags/") or remote_ref.startswith("refs/tags/"):
            continue
        refs.append((local_ref, local_sha, remote_ref, remote_sha))
    return refs


def build_push_payload(
    repo_root: Path,
    *,
    branch: str | None = None,
    base_sha: str | None = None,
    head_sha: str | None = None,
    remote_sha: str | None = None,
    default_branch_override: str | None = None,
    session_path: Path | None = None,
    agent: str = "antigravity-cli",
    hook_name: str = "pre-push",
    gemini_dir: Path | None = None,
    agy_dir: Path | None = None,
) -> tuple[dict[str, Any], Path | None]:
    """Collect git context, find/trim session, redact secrets, and build IngestPayload."""
    repo_ref = get_repo_ref(repo_root, default_branch_override=default_branch_override)
    effective_branch = branch or get_current_branch(repo_root)
    effective_head = head_sha or get_head_sha(repo_root)
    effective_base = base_sha or resolve_base_sha(
        repo_root,
        head_sha=effective_head,
        branch=effective_branch,
        default_branch=repo_ref["default_branch"],
        remote_sha=remote_sha,
    )

    commits = get_commits(repo_root, effective_base, effective_head)
    cutoff_time = get_oldest_commit_parent_time(repo_root, commits, effective_base)
    raw_diff = get_unified_diff(repo_root, effective_base, effective_head)
    raw_changed_files = get_changed_files(repo_root, effective_base, effective_head)

    selected_session: Path | None
    if session_path is not None:
        if not session_path.is_file():
            raise FileNotFoundError(f"Session file not found: {session_path}")
        selected_session = session_path
    else:
        if agent == "antigravity-cli":
            selected_session = find_agy_session(repo_root, after=cutoff_time, agy_dir=agy_dir)
        else:
            selected_session = find_gemini_session(
                repo_root, after=cutoff_time, gemini_dir=gemini_dir
            )

    raw_session: dict[str, Any] | None = None
    if selected_session is not None:
        if agent == "antigravity-cli":
            agent_version = get_agy_cli_version()
        elif agent == "gemini-cli":
            agent_version = get_gemini_cli_version()
        else:
            agent_version = None
        raw_session = load_and_trim_session(
            selected_session, agent=agent, agent_version=agent_version,
            repo_root=repo_root, base_sha=effective_base,
        )

    # Redact diff, changed file contents, and session lines with unified counts.
    scanner = SecretScanner(repo_root)
    redactions: dict[str, int] = {}

    scrubbed_diff, redactions = scanner.redact_value(raw_diff, redactions)

    scrubbed_files: list[dict[str, Any]] = []
    for cf in raw_changed_files:
        entry = dict(cf)
        if isinstance(entry.get("base_content"), str):
            entry["base_content"], redactions = scanner.redact_value(
                entry["base_content"], redactions
            )
        if isinstance(entry.get("head_content"), str):
            entry["head_content"], redactions = scanner.redact_value(
                entry["head_content"], redactions
            )
        scrubbed_files.append(entry)

    scrubbed_session: dict[str, Any] | None = None
    if raw_session is not None:
        scrubbed_lines, redactions = scanner.redact_value(raw_session["lines"], redactions)
        scrubbed_session = {
            "agent": raw_session["agent"],
            "agent_version": raw_session["agent_version"],
            "file_name": raw_session["file_name"],
            "lines": scrubbed_lines,
        }

    payload = build_ingest_payload(
        repo=repo_ref,
        branch=effective_branch,
        base_sha=effective_base,
        head_sha=effective_head,
        commits=commits,
        diff=scrubbed_diff,
        changed_files=scrubbed_files,
        session=scrubbed_session,
        redactions=redactions,
        hook_name=hook_name,
    )
    return payload, selected_session


def run_pre_push_hook(
    *,
    server_override: str | None = None,
    token_override: str | None = None,
    stdin_text: str | None = None,
    cwd: Path | None = None,
) -> int:
    """Invoked by git pre-push hook. Never blocks a push (always returns 0)."""
    try:
        raw_stdin = stdin_text if stdin_text is not None else sys.stdin.read()
        refs = parse_pre_push_refs(raw_stdin)
        if not refs:
            return 0

        repo_root = get_repo_root(cwd)
        cfg = resolve_repo_config(
            repo_root,
            server_override=server_override,
            token_override=token_override,
        )

        for local_ref, local_sha, _remote_ref, remote_sha in refs:
            branch = (
                local_ref.removeprefix("refs/heads/")
                if local_ref.startswith("refs/heads/")
                else local_ref
            )
            payload, _session_path = build_push_payload(
                repo_root,
                branch=branch,
                head_sha=local_sha,
                remote_sha=remote_sha,
                default_branch_override=cfg.default_branch,
                hook_name="pre-push",
            )
            resp = send_ingest_payload(
                cfg.server_url,
                payload,
                token=cfg.token,
                timeout_s=cfg.timeout_s,
            )
            print(
                format_ingest_result(
                    resp,
                    branch=branch,
                    head_sha=local_sha,
                    redactions=payload["redactions"],
                    has_session=payload["session"] is not None,
                )
            )
        return 0
    except Exception as exc:
        print(f"Unpack warning: {exc}", file=sys.stderr)
        return 0
