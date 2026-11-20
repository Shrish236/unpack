"""Source abstractions for reading repository files from filesystem or git revisions."""

from __future__ import annotations

import os
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path

IGNORE_DIRS = {
    ".git", ".venv", "venv", "env", "node_modules", "build", "dist",
    "__pycache__", ".tox", ".eggs", "site-packages", ".pytest_cache",
    ".hypothesis", ".cache"
}


class Source(ABC):
    """Abstract file source for graph extraction."""

    @abstractmethod
    def list_files(self) -> list[str]:
        """Return list of repo-relative python file paths."""
        pass

    @abstractmethod
    def read(self, path: str) -> bytes:
        """Read file contents as raw bytes."""
        pass


class FsSource(Source):
    """Reads files directly from a filesystem directory."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def list_files(self) -> list[str]:
        res: list[str] = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            # Prune ignored directories in place
            dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.endswith(".egg-info")]
            for f in filenames:
                if f.endswith(".py"):
                    full_p = Path(dirpath) / f
                    rel_p = full_p.relative_to(self.root).as_posix()
                    res.append(rel_p)
        res.sort()
        return res

    def read(self, path: str) -> bytes:
        full_p = self.root / path
        return full_p.read_bytes()


class GitSource(Source):
    """Reads files directly from git objects at a revision without checkout."""

    def __init__(self, repo_path: str | Path, rev: str) -> None:
        self.repo_path = Path(repo_path).resolve()
        self.rev = rev

    def list_files(self) -> list[str]:
        cmd = ["git", "-C", str(self.repo_path), "ls-tree", "-r", "--name-only", self.rev]
        p = subprocess.run(cmd, capture_output=True, text=True, check=True)
        files = []
        for line in p.stdout.splitlines():
            line = line.strip()
            if not line.endswith(".py"):
                continue
            parts = line.split("/")
            if any(part in IGNORE_DIRS or part.endswith(".egg-info") for part in parts):
                continue
            files.append(line)
        files.sort()
        return files

    def read(self, path: str) -> bytes:
        obj_spec = f"{self.rev}:{path}"
        cmd = ["git", "-C", str(self.repo_path), "cat-file", "-p", obj_spec]
        p = subprocess.run(cmd, capture_output=True, check=True)
        return p.stdout
