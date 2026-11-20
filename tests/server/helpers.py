"""Builders for ingest payloads and repo rows used across the server tests."""

from __future__ import annotations

import gzip
import json
from typing import Any

from server.app.db import session_scope
from server.app.models import Repo
from server.app.security import hash_token, new_ingest_token

from .conftest import Origin


async def create_repo(owner: str = "o", name: str = "r", *, installation_id: int | None = 123,
                      status: str = "active", remote_url: str | None = None) -> tuple[int, str]:
    token = new_ingest_token()
    async with session_scope() as session:
        repo = Repo(owner=owner, name=name, remote_url=remote_url or f"https://github.com/{owner}/{name}.git",
                    default_branch="main", installation_id=installation_id,
                    ingest_token_hash=hash_token(token), status=status)
        session.add(repo)
        await session.flush()
        return repo.id, token


def origin_payload(origin: Origin, *, branch: str = "feature/x", owner: str = "o", name: str = "r",
                   with_head_content: bool = True, session: dict | None = None) -> dict[str, Any]:
    head = origin.head_sha
    changed = []
    for rel in ("pkg/core.py",):
        changed.append({
            "path": rel, "old_path": None, "status": "M", "is_binary": False,
            "base_content": origin.file_at(origin.base_sha, rel),
            "head_content": origin.file_at(head, rel) if with_head_content else None,
            "truncated": not with_head_content,
        })
    return {
        "schema_version": 1,
        "repo": {"remote_url": f"https://github.com/{owner}/{name}.git", "owner": owner, "name": name,
                 "default_branch": "main"},
        "branch": branch,
        "base_sha": origin.base_sha,
        "head_sha": head,
        "commits": [{"sha": head, "message": "change", "author_time": "2026-11-19T14:20:00Z"}],
        "diff": origin.diff(),
        "changed_files": changed,
        "session": session,
        "redactions": {},
        "client": {"cli_version": "0.1.0", "os": "linux", "hook": "pre-push"},
    }


def gzip_json(obj: dict[str, Any]) -> bytes:
    return gzip.compress(json.dumps(obj).encode("utf-8"))


def ingest_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json",
            "Content-Encoding": "gzip"}


BASE_CORE = '''def helper(x):
    return x + 1


def compute(x):
    return helper(x) * 2


class Client:
    def send(self, value):
        return compute(value)
'''

HEAD_CORE = '''def helper(x):
    return x + 10


def compute(x):
    return helper(x) * 2


class Client:
    def send(self, value):
        return compute(value)


def brand_new():
    return 0
'''

BASE_TEST = '''from pkg.core import compute


def test_compute():
    assert compute(1) == 4
'''


def standard_files() -> tuple[dict[str, str], dict[str, str]]:
    base = {"pkg/__init__.py": "", "pkg/core.py": BASE_CORE, "tests/test_core.py": BASE_TEST}
    head = {"pkg/core.py": HEAD_CORE}
    return base, head
