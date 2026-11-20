"""File sources: a working tree on disk, or a git revision read without checkout."""
from __future__ import annotations

import os
import subprocess

IGNORE_DIRS = {".git", ".venv", "venv", "env", "node_modules", "build", "dist", "__pycache__",
               ".tox", ".eggs", "site-packages", ".mypy_cache", ".pytest_cache",
               ".code-review-graph", ".ruff_cache"}


class FsSource:
    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        self.label = "worktree"

    def list_files(self) -> list:
        out = []
        for dp, dns, fns in os.walk(self.root):
            dns[:] = sorted(d for d in dns if d not in IGNORE_DIRS and not d.endswith(".egg-info"))
            for fn in sorted(fns):
                if fn.endswith(".py"):
                    out.append(os.path.relpath(os.path.join(dp, fn), self.root).replace(os.sep, "/"))
        return out

    def read(self, path: str) -> bytes:
        with open(os.path.join(self.root, path), "rb") as f:
            return f.read()


class GitSource:
    """Reads blobs of `rev` straight from the object database (no checkout)."""

    def __init__(self, root: str, rev: str):
        self.root = os.path.abspath(root)
        self.rev = rev
        self.label = rev
        self._proc = None
        out = subprocess.run(["git", "-C", self.root, "ls-tree", "-r", "-z", self.rev],
                             check=True, capture_output=True).stdout
        self._blobs = {}
        for ent in out.split(b"\0"):
            if not ent:
                continue
            meta, p = ent.split(b"\t", 1)
            mode, typ, sha = meta.decode().split()
            if typ == "blob":
                self._blobs[p.decode("utf-8", "replace")] = sha

    def list_files(self) -> list:
        out = []
        for p in sorted(self._blobs):
            if not p.endswith(".py"):
                continue
            if any(part in IGNORE_DIRS or part.endswith(".egg-info") for part in p.split("/")[:-1]):
                continue
            out.append(p)
        return out

    def read(self, path: str) -> bytes:
        """Blob contents through one persistent `git cat-file --batch` process."""
        if self._proc is None or self._proc.poll() is not None:
            self._proc = subprocess.Popen(["git", "-C", self.root, "cat-file", "--batch"],
                                          stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        sha = self._blobs[path]
        self._proc.stdin.write(sha.encode() + b"\n")
        self._proc.stdin.flush()
        header = self._proc.stdout.readline().split()
        size = int(header[2])
        data = self._proc.stdout.read(size)
        self._proc.stdout.read(1)               # trailing newline
        return data

    def close(self):
        if self._proc is not None:
            try:
                self._proc.stdin.close()
                self._proc.wait(timeout=5)
            except Exception:
                self._proc.kill()
            self._proc = None

    def __del__(self):
        self.close()
