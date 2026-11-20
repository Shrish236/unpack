"""Git inspection helpers for collecting commits, diffs, and changed files."""

from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

ZERO_SHA = "0" * 40
EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
MAX_FILE_BYTES = 1_000_000


class GitError(RuntimeError):
    """Raised when a required git command fails."""


def run_git_bytes(args: list[str], cwd: Path | None = None, check: bool = True) -> bytes:
    """Run git and return raw stdout bytes."""
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise GitError(f"git {' '.join(args)} failed: {err}")
    return proc.stdout


def run_git(args: list[str], cwd: Path | None = None, check: bool = True) -> str:
    """Run git and return UTF-8 decoded stdout."""
    return run_git_bytes(args, cwd=cwd, check=check).decode("utf-8", errors="replace")


def get_repo_root(cwd: Path | None = None) -> Path:
    """Return canonical realpath to the git repository root."""
    raw = run_git(["rev-parse", "--show-toplevel"], cwd=cwd).strip()
    return Path(os.path.realpath(raw))


def get_hooks_dir(repo_root: Path) -> Path:
    """Return the resolved git hooks directory (supports worktrees and core.hooksPath)."""
    raw = run_git(["rev-parse", "--git-path", "hooks"], cwd=repo_root).strip()
    hooks_path = Path(raw)
    if not hooks_path.is_absolute():
        hooks_path = repo_root / hooks_path
    return hooks_path


def parse_remote_url(remote_url: str, fallback_name: str = "repo") -> tuple[str, str]:
    """Extract (owner, name) from SSH, HTTPS, or local git remote URLs."""
    cleaned = remote_url.strip().rstrip("/")
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]

    # git@github.com:owner/name
    scp_match = re.match(r"^[^@]+@[^:]+:(.+)$", cleaned)
    if scp_match:
        path_part = scp_match.group(1).strip("/")
        segments = [s for s in path_part.split("/") if s]
        if len(segments) >= 2:
            return segments[-2], segments[-1]
        if len(segments) == 1:
            return "local", segments[0]

    # https://github.com/owner/name or ssh://git@github.com/owner/name
    url_match = re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://[^/]+/(.+)$", cleaned)
    if url_match:
        path_part = url_match.group(1).strip("/")
        segments = [s for s in path_part.split("/") if s]
        if len(segments) >= 2:
            return segments[-2], segments[-1]
        if len(segments) == 1:
            return "local", segments[0]

    # Local filesystem path (e.g. /tmp/bare/owner/repo)
    segments = [s for s in Path(cleaned).parts if s not in ("/", "\\")]
    if len(segments) >= 2:
        return segments[-2], segments[-1]
    if len(segments) == 1:
        return "local", segments[0]
    return "local", fallback_name


def detect_default_branch(repo_root: Path) -> str:
    """Detect the repository default branch from origin/HEAD or common branch names."""
    proc = subprocess.run(
        ["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if proc.returncode == 0:
        ref = proc.stdout.strip()
        if ref.startswith("origin/"):
            return ref.removeprefix("origin/")
        if ref:
            return ref

    for candidate in ("origin/main", "origin/master", "main", "master"):
        if _ref_exists(repo_root, candidate):
            return candidate.removeprefix("origin/")
    return "main"


def get_repo_ref(
    repo_root: Path, default_branch_override: str | None = None
) -> dict[str, Any]:
    """Build RepoRef matching contract/schema/ingest_payload.json."""
    remote_url: str | None = None
    proc = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        remote_url = proc.stdout.strip()

    if remote_url:
        owner, name = parse_remote_url(remote_url, fallback_name=repo_root.name)
    else:
        owner, name = "local", repo_root.name

    default_branch = default_branch_override or detect_default_branch(repo_root)
    return {
        "owner": owner,
        "name": name,
        "remote_url": remote_url,
        "default_branch": default_branch,
    }


def get_current_branch(repo_root: Path) -> str:
    """Return current branch name (or 'HEAD' when detached)."""
    proc = subprocess.run(
        ["git", "symbolic-ref", "--short", "HEAD"],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()
    return "HEAD"


def get_head_sha(repo_root: Path, rev: str = "HEAD") -> str:
    """Resolve a revision (default HEAD) to its full 40-char commit SHA."""
    return run_git(["rev-parse", rev], cwd=repo_root).strip()


def _ref_exists(repo_root: Path, ref: str) -> bool:
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", ref],
        cwd=str(repo_root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return proc.returncode == 0


def resolve_base_sha(
    repo_root: Path,
    head_sha: str,
    branch: str,
    default_branch: str,
    remote_sha: str | None = None,
) -> str:
    """Resolve base SHA using merge-base against the default branch for full PR diffs.

    Falls back to remote_sha, head_sha^, or the empty tree SHA when pushing directly
    to the default branch or when no default branch ref exists.
    """
    if branch != default_branch:
        for base_ref in (f"origin/{default_branch}", default_branch):
            if _ref_exists(repo_root, base_ref):
                proc = subprocess.run(
                    ["git", "merge-base", head_sha, base_ref],
                    cwd=str(repo_root),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                )
                if proc.returncode == 0:
                    mb = proc.stdout.strip()
                    if mb and mb != head_sha:
                        return mb

    if remote_sha and remote_sha != ZERO_SHA and remote_sha != head_sha:
        if _ref_exists(repo_root, remote_sha):
            return remote_sha

    # Fallback: parent of head_sha (or empty tree for initial root commit)
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{head_sha}^"],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()

    return EMPTY_TREE_SHA


def get_commits(repo_root: Path, base_sha: str, head_sha: str) -> list[dict[str, str]]:
    """Return chronological commits between base_sha and head_sha."""
    rev_range = head_sha if base_sha == EMPTY_TREE_SHA else f"{base_sha}..{head_sha}"
    output = run_git(
        ["log", "--reverse", "--format=%H%x1f%aI%x1f%B%x1e", rev_range],
        cwd=repo_root,
        check=False,
    )
    commits: list[dict[str, str]] = []
    for raw_entry in output.split("\x1e"):
        entry = raw_entry.strip()
        if not entry:
            continue
        parts = entry.split("\x1f", 2)
        if len(parts) < 3:
            continue
        sha, author_time, message = parts
        commits.append(
            {
                "sha": sha.strip(),
                "message": message.strip(),
                "author_time": author_time.strip(),
            }
        )
    return commits


def _parse_iso_datetime(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def get_oldest_commit_parent_time(
    repo_root: Path, commits: list[dict[str, str]], base_sha: str
) -> datetime | None:
    """Return timestamp of the oldest pushed commit's parent (used for session cutoff)."""
    candidates: list[str] = []
    if commits:
        candidates.append(f"{commits[0]['sha']}^")
    if base_sha and base_sha != EMPTY_TREE_SHA:
        candidates.append(base_sha)

    for rev in candidates:
        proc = subprocess.run(
            ["git", "show", "-s", "--format=%cI", rev],
            cwd=str(repo_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            parsed = _parse_iso_datetime(proc.stdout.strip())
            if parsed is not None:
                return parsed

    if commits:
        return _parse_iso_datetime(commits[0]["author_time"])
    return None


def get_unified_diff(repo_root: Path, base_sha: str, head_sha: str) -> str:
    """Return unified diff (-U3) between base_sha and head_sha."""
    return run_git(["diff", "-U3", base_sha, head_sha], cwd=repo_root)


def _read_blob_bytes(repo_root: Path, sha: str, path: str) -> bytes | None:
    if sha in (EMPTY_TREE_SHA, ZERO_SHA):
        return None
    proc = subprocess.run(
        ["git", "show", f"{sha}:{path}"],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout


def _decode_utf8_or_binary(raw: bytes | None, max_bytes: int) -> tuple[str | None, bool, bool]:
    """Decode blob bytes. Returns (text_or_none, is_binary, truncated)."""
    if raw is None:
        return None, False, False
    if b"\x00" in raw:
        return None, True, False
    if len(raw) > max_bytes:
        # Check prefix for binary bytes before marking truncated text
        if b"\x00" in raw[:8192]:
            return None, True, False
        try:
            raw[:8192].decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            # Cut boundary may split a multi-byte char; re-check without trailing 3 bytes
            try:
                raw[:8189].decode("utf-8", errors="strict")
            except UnicodeDecodeError:
                return None, True, False
        return None, False, True
    try:
        return raw.decode("utf-8"), False, False
    except UnicodeDecodeError:
        return None, True, False


def get_changed_files(
    repo_root: Path,
    base_sha: str,
    head_sha: str,
    max_bytes: int = MAX_FILE_BYTES,
) -> list[dict[str, Any]]:
    """Collect ChangedFilePayload entries for all files changed between base_sha and head_sha."""
    raw = run_git_bytes(["diff", "--name-status", "-M", "-z", base_sha, head_sha], cwd=repo_root)
    if not raw:
        return []

    tokens = raw.split(b"\x00")
    changed: list[dict[str, Any]] = []
    idx = 0
    while idx < len(tokens):
        status_bytes = tokens[idx]
        idx += 1
        if not status_bytes:
            continue
        status_raw = status_bytes.decode("utf-8", errors="replace")
        code = status_raw[0]

        old_path: str | None = None
        if code in ("R", "C"):
            if idx + 1 >= len(tokens):
                break
            old_path = tokens[idx].decode("utf-8", errors="replace")
            path = tokens[idx + 1].decode("utf-8", errors="replace")
            idx += 2
            status = "R" if code == "R" else "A"
            if status == "A":
                old_path = None
        else:
            if idx >= len(tokens):
                break
            path = tokens[idx].decode("utf-8", errors="replace")
            idx += 1
            if code in ("A", "M", "D"):
                status = code
            else:
                status = "M"

        base_bytes = (
            None
            if status == "A"
            else _read_blob_bytes(repo_root, base_sha, old_path or path)
        )
        head_bytes = None if status == "D" else _read_blob_bytes(repo_root, head_sha, path)

        base_text, base_bin, base_trunc = _decode_utf8_or_binary(base_bytes, max_bytes)
        head_text, head_bin, head_trunc = _decode_utf8_or_binary(head_bytes, max_bytes)

        is_binary = base_bin or head_bin
        truncated = (not is_binary) and (base_trunc or head_trunc)
        if is_binary:
            base_text = None
            head_text = None

        changed.append(
            {
                "path": path,
                "old_path": old_path,
                "status": status,
                "is_binary": is_binary,
                "base_content": base_text,
                "head_content": head_text,
                "truncated": truncated,
            }
        )

    return changed
