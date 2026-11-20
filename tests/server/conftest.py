"""Shared fixtures: test settings, Postgres schema, a real git origin, a mocked GitHub, and the ASGI client."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Settings are read at import time, so the test environment is set before any server module loads.
# Each pytest-xdist worker gets its own database, so workers can truncate tables without touching each other.
_WORKER = os.environ.get("PYTEST_XDIST_WORKER", "main")
_TEST_DB = f"unpack_test_{_WORKER}".replace("-", "_")


def _ensure_database(name: str) -> None:
    import psycopg2

    conn = psycopg2.connect(host="localhost", port=5432, user="unpack", password="unpackpass", dbname="postgres")
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
        if cur.fetchone() is None:
            cur.execute(f'CREATE DATABASE "{name}" OWNER unpack')
    conn.close()


_ensure_database(_TEST_DB)
os.environ.setdefault("UNPACK_BASE_URL", "https://unpack.test")
# Forced, not defaulted: a shell that exports DATABASE_URL must not send tests to a shared database.
os.environ["DATABASE_URL"] = f"postgresql://unpack:unpackpass@localhost:5432/{_TEST_DB}"
os.environ.setdefault("SESSION_SECRET", "test_session_secret_value_that_is_long_enough_32")
os.environ.setdefault("RENDER_TOKEN_SECRET", "test_render_secret_value_that_is_long_enough_32")
os.environ.setdefault("ADMIN_TOKEN", "test_admin_token_value_that_is_long_enough_32")
os.environ.setdefault("TOKEN_ENCRYPTION_KEY", "Yx4bq7Pn1hjVQ1xq0mD3xV0aXlYl7vHk1m3Pz0cQe6U=")
os.environ["DATA_DIR"] = f"/tmp/unpack-test-data-{_WORKER}"

import httpx  # noqa: E402
import pytest  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from sqlalchemy import text  # noqa: E402

from server.app.config import settings  # noqa: E402
from server.app.db import Base, get_engine, reset_engine  # noqa: E402
from server.app.main import app  # noqa: E402
from server.app.github.service import GitHubService  # noqa: E402
from server.app import services  # noqa: E402
from server.app.security import hash_token  # noqa: E402

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
    "PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "/root"),
}


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, env=GIT_ENV, check=True,
                          capture_output=True, text=True).stdout.strip()


def write_files(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


class Origin:
    """A working repo with a base commit, plus a head commit that is not on the origin yet."""

    def __init__(self, root: Path, base_files: dict[str, str], head_files: dict[str, str]):
        self.work = root / "work"
        self.work.mkdir(parents=True)
        git(self.work, "init", "-q", "-b", "main")
        write_files(self.work, base_files)
        git(self.work, "add", "-A")
        git(self.work, "commit", "-q", "-m", "base")
        self.base_sha = git(self.work, "rev-parse", "HEAD")
        # The origin holds only the base commit, so the head is unknown to GitHub until it is pushed.
        self.bare = root / "origin.git"
        subprocess.run(["git", "clone", "-q", "--bare", str(self.work), str(self.bare)], check=True, env=GIT_ENV)
        write_files(self.work, head_files)
        git(self.work, "add", "-A")
        git(self.work, "commit", "-q", "-m", "change")
        self.head_sha = git(self.work, "rev-parse", "HEAD")
        self.remote_url = str(self.bare)

    def diff(self) -> str:
        return git(self.work, "diff", "-U3", self.base_sha, self.head_sha) + "\n"

    def file_at(self, sha: str, path: str) -> str:
        return git(self.work, "show", f"{sha}:{path}")

    def push_head_to_origin(self) -> None:
        git(self.work, "push", "-q", str(self.bare), "HEAD:refs/heads/main")


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    """Every test gets its own data directory and an empty in-memory graph cache.

    Repository and graph caches are keyed by ids and SHAs that restart in each test, so sharing either
    would let one test read another test's graph.
    """
    from server.app.pipeline import repos as repos_module

    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path / "data"))
    repos_module._lru.clear()
    yield
    repos_module._lru.clear()


@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    return tmp_path / "data"


@pytest.fixture
async def db_ready():
    """Fresh schema on the test database for every test (tables are truncated, not dropped)."""
    reset_engine()
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        await conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    yield
    await get_engine().dispose()
    reset_engine()


@pytest.fixture
def private_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()


class FakeGitHub:
    """Routes the GitHub calls the server makes. Tests set the state and read the recorded writes."""

    def __init__(self) -> None:
        self.open_prs: list[dict] = []
        self.compare_status: dict[str, dict] = {}  # head sha -> {"status","ahead_by","behind_by"}
        self.comments: dict[int, dict] = {}  # id -> comment
        self.created: list[dict] = []
        self.updated: list[dict] = []
        self.viewer_access: int = 200
        self.installation_for: dict[str, int | None] = {}
        self.pr_state: dict[int, dict] = {}
        self.next_comment_id = 1000
        self.calls: list[tuple[str, str]] = []
        self.installation_repos: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        method, path = request.method, request.url.path
        self.calls.append((method, path))
        if method == "POST" and path.endswith("/access_tokens"):
            expires = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
            return httpx.Response(201, json={"token": "ghs_installation_token", "expires_at": expires})
        if method == "GET" and path == "/user":
            return httpx.Response(200, json={"id": 42, "login": "octo", "avatar_url": "https://a.test/x.png"})
        if method == "GET" and path == "/installation/repositories":
            return httpx.Response(200, json={"repositories": self.installation_repos})
        if method == "GET" and path.endswith("/installation"):
            owner_repo = path.split("/")[2:4]
            install = self.installation_for.get("/".join(owner_repo), 123)
            if install is None:
                return httpx.Response(404, json={"message": "Not Found"})
            return httpx.Response(200, json={"id": install})
        if method == "GET" and path.endswith("/pulls"):
            return httpx.Response(200, json=self.open_prs)
        if method == "GET" and "/pulls/" in path:
            number = int(path.rsplit("/", 1)[1])
            return httpx.Response(200, json=self.pr_state.get(number, {"state": "open"}))
        if method == "GET" and "/compare/" in path:
            head = path.split("...")[1]
            return httpx.Response(200, json=self.compare_status.get(head, {"status": "identical", "ahead_by": 0, "behind_by": 0}))
        if method == "GET" and path.endswith("/comments"):
            return httpx.Response(200, json=list(self.comments.values()))
        if method == "POST" and path.endswith("/comments"):
            self.next_comment_id += 1
            comment = {"id": self.next_comment_id, "body": json_body(request),
                       "html_url": f"https://github.com/o/r/pull/1#issuecomment-{self.next_comment_id}"}
            self.comments[comment["id"]] = comment
            self.created.append(comment)
            return httpx.Response(201, json=comment)
        if method == "PATCH" and "/issues/comments/" in path:
            comment_id = int(path.rsplit("/", 1)[1])
            if comment_id not in self.comments:
                return httpx.Response(404, json={"message": "Not Found"})
            self.comments[comment_id]["body"] = json_body(request)
            self.updated.append(self.comments[comment_id])
            return httpx.Response(200, json=self.comments[comment_id])
        if method == "GET" and path.count("/") == 3 and path.startswith("/repos/"):
            return httpx.Response(self.viewer_access, json={"full_name": "o/r"})
        return httpx.Response(500, json={"message": f"unmocked {method} {path}"})


def json_body(request: httpx.Request) -> str:
    import json

    return json.loads(request.content.decode("utf-8"))["body"]


@pytest.fixture
def fake_github(private_key_pem, monkeypatch):
    fake = FakeGitHub()
    svc = GitHubService(
        settings.GITHUB_API_URL,
        app_id="1",
        private_key_pem=private_key_pem,
        transport=httpx.MockTransport(fake.handler),
    )
    services.set_github(svc)
    monkeypatch.setattr(settings, "GITHUB_APP_ID", "1")
    monkeypatch.setattr(settings, "GITHUB_WEBHOOK_SECRET", "whsec_test_webhook_secret_value_long")
    monkeypatch.setattr(settings, "GITHUB_CLIENT_ID", "client-id")
    monkeypatch.setattr(settings, "GITHUB_CLIENT_SECRET", "client-secret")
    yield fake
    services.set_github(None)


@pytest.fixture
async def client(db_ready):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://unpack.test") as http:
        yield http


async def drain_jobs(max_rounds: int = 50) -> int:
    """Runs queued jobs in the calling process, the way a worker slot would."""
    from server.app.jobs import queue
    from server.app.jobs.handlers import dispatch

    ran = 0
    for _ in range(max_rounds):
        job = await queue.claim()
        if job is None:
            return ran
        await dispatch(job["type"], job["payload"])
        await queue.finish(job["id"])
        ran += 1
    return ran


def ingest_token_for(name: str) -> tuple[str, str]:
    token = f"unp_{name}_" + "A" * 36
    return token, hash_token(token)
