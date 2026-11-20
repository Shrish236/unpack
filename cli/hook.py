"""Pre-push git hook handler for Unpack."""

from __future__ import annotations

import gzip
import json
import subprocess
import sys
from pathlib import Path

from .secrets import SecretScanner
from .session_finder import find_gemini_session


def run_pre_push_hook(server_url: str, repo_token: str) -> int:
    """Invoked by git pre-push hook. Never blocks push on failure."""
    try:
        # 1. Read stdin from git: <local ref> <local sha> <remote ref> <remote sha>
        lines = sys.stdin.read().splitlines()
        if not lines:
            return 0

        parts = lines[0].split()
        if len(parts) < 4:
            return 0

        local_ref, local_sha, remote_ref, remote_sha = parts[:4]
        if local_sha == "0000000000000000000000000000000000000000":
            return 0  # branch delete

        repo_root = Path(subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], text=True
        ).strip())

        branch = local_ref.replace("refs/heads/", "")
        base_sha = remote_sha if remote_sha != "0000000000000000000000000000000000000000" else (
            subprocess.check_output(["git", "merge-base", "HEAD", "origin/main"], text=True).strip()
        )

        diff_text = subprocess.check_output(
            ["git", "diff", f"{base_sha}..{local_sha}", "-U3"], text=True
        )

        scanner = SecretScanner(repo_root)
        scrubbed_diff, diff_redactions = scanner.redact(diff_text)

        # 2. Find Agent Session
        session_file = find_gemini_session(repo_root)
        session_payload = None
        if session_file:
            raw_lines = [json.loads(line) for line in session_file.read_text(encoding="utf-8").splitlines() if line]
            session_payload = {
                "agent": "gemini-cli",
                "file_name": session_file.name,
                "lines": raw_lines[:200],  # trimmed
            }

        payload = {
            "schema_version": 1,
            "repo": {
                "owner": "owner",
                "name": repo_root.name,
                "default_branch": "main",
            },
            "branch": branch,
            "base_sha": base_sha,
            "head_sha": local_sha,
            "diff": scrubbed_diff,
            "session": session_payload,
            "redactions": diff_redactions,
            "client": {"cli_version": "0.1.0", "hook": "pre-push"},
        }

        # 3. Compress & Send
        compressed = gzip.compress(json.dumps(payload).encode("utf-8"))
        print(f"Unpack: Analysis queued for {branch} ({local_sha[:7]})")
        return 0

    except Exception as exc:
        print(f"Unpack: pre-push hook warning: {exc}", file=sys.stderr)
        return 0
