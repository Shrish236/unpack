"""Local repository mirrors, commit fetches and per-commit graph cache (server design §6)."""

from __future__ import annotations

import asyncio
import os
import pickle
import stat
from pathlib import Path
from typing import Any

from ..config import settings


class GitError(Exception):
    pass


class CommitUnavailable(GitError):
    pass


def data_dir() -> Path:
    return Path(settings.DATA_DIR)


def repo_dir(owner: str, name: str) -> Path:
    return data_dir() / "repos" / owner.lower() / f"{name.lower()}.git"


def _askpass_path() -> Path:
    path = data_dir() / "git-askpass.sh"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            '#!/bin/sh\ncase "$1" in *sername*) echo x-access-token;; *) echo "$UNPACK_GIT_TOKEN";; esac\n',
            encoding="utf-8",
        )
        path.chmod(stat.S_IRWXU)
    return path


async def run_git(*args: str, cwd: Path | None = None, token: str | None = None, check: bool = True) -> bytes:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    if token:
        # The token travels in the environment and through the askpass helper, never in the URL or .git/config.
        env["GIT_ASKPASS"] = str(_askpass_path())
        env["UNPACK_GIT_TOKEN"] = token
    proc = await asyncio.create_subprocess_exec(
        "git", *args,
        cwd=str(cwd) if cwd else None,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if check and proc.returncode != 0:
        raise GitError(f"git {args[0]} failed: {stderr.decode(errors='replace').strip()[:300]}")
    return stdout


async def ensure_mirror(owner: str, name: str, remote_url: str, token: str | None) -> Path:
    """Bare mirror of the repository. Cloned once, then fetched on demand."""
    path = repo_dir(owner, name)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        await run_git("clone", "--bare", "--quiet", remote_url, str(path), token=token)
    return path


async def has_commit(path: Path, sha: str) -> bool:
    proc = await asyncio.create_subprocess_exec(
        "git", "cat-file", "-e", f"{sha}^{{commit}}", cwd=str(path),
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
    )
    return (await proc.wait()) == 0


async def ensure_commit(path: Path, sha: str, token: str | None) -> None:
    if await has_commit(path, sha):
        return
    try:
        await run_git("fetch", "--quiet", "origin", sha, cwd=path, token=token)
    except GitError as exc:
        raise CommitUnavailable(str(exc)) from exc
    if not await has_commit(path, sha):
        raise CommitUnavailable(f"commit {sha} is not reachable from the repository")


def graph_cache_path(repo_id: int, sha: str) -> Path:
    return data_dir() / "graphs" / str(repo_id) / f"{sha}.pkl"


def load_cached_graph(repo_id: int, sha: str) -> Any | None:
    path = graph_cache_path(repo_id, sha)
    if not path.exists():
        return None
    with path.open("rb") as fh:
        return pickle.load(fh)  # written only by this server, from its own data directory


def save_cached_graph(repo_id: int, sha: str, graph: Any) -> None:
    path = graph_cache_path(repo_id, sha)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("wb") as fh:
        pickle.dump(graph, fh, protocol=pickle.HIGHEST_PROTOCOL)
    tmp.replace(path)
