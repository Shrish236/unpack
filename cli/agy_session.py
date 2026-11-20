"""Locates Antigravity CLI (agy) sessions for a repository.

agy keeps a resume cache, ``cache/last_conversations.json``, that maps each workspace
directory to the most recent conversation id run there. The conversation's transcript is
``brain/<conversation id>/.system_generated/logs/transcript_full.jsonl``.

The cache holds only the latest conversation per folder, so older sessions in the same repo
are not found. Paths are compared case-insensitively, because Windows casing can differ
between the cache and the repo root.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

AGY_HOME = Path.home() / ".gemini" / "antigravity-cli"
TRANSCRIPT_RELATIVE = Path(".system_generated") / "logs" / "transcript_full.jsonl"


def _normalized(path: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.realpath(path)))


def resolve_agy_conversation(repo_root: Path, agy_dir: Path | None = None) -> str | None:
    """Return the conversation id last run in repo_root, or None."""
    base = agy_dir or AGY_HOME
    try:
        data = json.loads((base / "cache" / "last_conversations.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    target = _normalized(str(repo_root))
    for key, value in data.items():
        if isinstance(key, str) and isinstance(value, str) and _normalized(key) == target:
            return value
    return None


def find_agy_session(
    repo_root: Path,
    *,
    after: datetime | None = None,
    agy_dir: Path | None = None,
) -> Path | None:
    """Return the transcript for the repo's latest agy conversation, if it changed after `after`."""
    base = agy_dir or AGY_HOME
    conversation_id = resolve_agy_conversation(repo_root, agy_dir=base)
    if not conversation_id:
        return None
    transcript = base / "brain" / conversation_id / TRANSCRIPT_RELATIVE
    if not transcript.is_file():
        return None
    if after is not None:
        if after.tzinfo is None:
            after = after.replace(tzinfo=timezone.utc)
        modified = datetime.fromtimestamp(transcript.stat().st_mtime, tz=timezone.utc)
        if modified < after:
            return None
    return transcript


def get_agy_cli_version(timeout_s: float = 1.0) -> str | None:
    """Return the first line of `agy --version`, or None if it is unavailable."""
    exe = shutil.which("agy")
    if exe is None:
        return None
    try:
        proc = subprocess.run(
            [exe, "--version"], capture_output=True, text=True, timeout=timeout_s, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    lines = (proc.stdout or "").strip().splitlines()
    return lines[0].strip() if lines else None
