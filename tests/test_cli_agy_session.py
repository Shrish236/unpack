"""Antigravity CLI (agy) session discovery via the resume cache."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cli import agy_session
from cli.agy_session import find_agy_session, get_agy_cli_version, resolve_agy_conversation

CONV = "47712618-c087-48f9-879e-b096fa17328e"


def _make_agy_home(base: Path, workspace: str, conversation: str = CONV) -> Path:
    (base / "cache").mkdir(parents=True)
    (base / "cache" / "last_conversations.json").write_text(
        json.dumps({workspace: conversation}), encoding="utf-8"
    )
    transcript = base / "brain" / conversation / ".system_generated" / "logs" / "transcript_full.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text('{"step_index":0,"type":"USER_INPUT","content":"hi"}\n', encoding="utf-8")
    return transcript


def test_finds_transcript_for_repo_root(tmp_path: Path):
    repo = tmp_path / "shop"
    repo.mkdir()
    agy_home = tmp_path / "agy"
    transcript = _make_agy_home(agy_home, str(repo))

    assert resolve_agy_conversation(repo, agy_dir=agy_home) == CONV
    assert find_agy_session(repo, agy_dir=agy_home) == transcript


def test_match_ignores_path_case(tmp_path: Path):
    repo = tmp_path / "shop"
    repo.mkdir()
    agy_home = tmp_path / "agy"
    transcript = _make_agy_home(agy_home, str(repo).upper())

    assert find_agy_session(repo, agy_dir=agy_home) == transcript


def test_other_repo_has_no_session(tmp_path: Path):
    repo = tmp_path / "shop"
    repo.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    agy_home = tmp_path / "agy"
    _make_agy_home(agy_home, str(other))

    assert find_agy_session(repo, agy_dir=agy_home) is None


def test_transcript_older_than_cutoff_is_skipped(tmp_path: Path):
    repo = tmp_path / "shop"
    repo.mkdir()
    agy_home = tmp_path / "agy"
    transcript = _make_agy_home(agy_home, str(repo))
    old = datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp()
    os.utime(transcript, (old, old))

    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    assert find_agy_session(repo, after=cutoff, agy_dir=agy_home) is None
    assert find_agy_session(repo, agy_dir=agy_home) == transcript


def test_missing_cache_returns_none(tmp_path: Path):
    assert find_agy_session(tmp_path, agy_dir=tmp_path / "missing") is None


def test_version_is_none_when_agy_not_installed(monkeypatch):
    monkeypatch.setattr(agy_session.shutil, "which", lambda _name: None)
    assert get_agy_cli_version() is None
