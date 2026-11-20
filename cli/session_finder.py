"""Locates agent sessions on the local developer machine."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def find_gemini_session(repo_root: Path) -> Path | None:
    """Find the most recent Gemini CLI session for this repository."""
    gemini_dir = Path.home() / ".gemini"
    projects_file = gemini_dir / "projects.json"

    short_id = None
    if projects_file.exists():
        try:
            data = json.loads(projects_file.read_text(encoding="utf-8"))
            projects = data.get("projects", {})
            abs_root = str(repo_root.resolve())
            short_id = projects.get(abs_root)
        except Exception:
            pass

    if not short_id:
        short_id = hashlib.sha256(str(repo_root.resolve()).encode("utf-8")).hexdigest()[:8]

    chats_dir = gemini_dir / "tmp" / short_id / "chats"
    if not chats_dir.exists():
        return None

    sessions = list(chats_dir.glob("session-*.jsonl"))
    if not sessions:
        return None

    # Pick latest modified session
    sessions.sort(key=lambda s: s.stat().st_mtime, reverse=True)
    return sessions[0]
