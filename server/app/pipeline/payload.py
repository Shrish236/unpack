"""Payload helpers: unified diff hunks and an in-memory head source (server design §5.1, §6).

The hook sends changed files with their contents, because a pre-push hook runs before GitHub
has the commit. The head graph is built from the base commit plus those contents, so the
analysis does not depend on timing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from unpack_graph.source import IGNORE_DIRS, Source

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass
class Hunk:
    new_start: int
    new_end: int
    patch: str


def parse_diff_hunks(diff: str) -> dict[str, list[Hunk]]:
    """Hunks keyed by the new-side path (or the old path for deletions)."""
    result: dict[str, list[Hunk]] = {}
    current: str | None = None
    old_name: str | None = None
    hunk_lines: list[str] | None = None
    header: tuple[int, int] | None = None

    def flush() -> None:
        if current and hunk_lines is not None and header is not None:
            start, count = header
            end = start + max(count, 1) - 1
            result.setdefault(current, []).append(Hunk(start, end, "\n".join(hunk_lines)))

    for line in diff.splitlines():
        if line.startswith("diff --git "):
            # Content lines always start with ' ', '+', '-' or '\\', so this starts a new file.
            flush()
            hunk_lines, header, current = None, None, None
            continue
        match = HUNK_RE.match(line)
        if match:
            flush()
            new_start = int(match.group(3))
            new_count = int(match.group(4)) if match.group(4) is not None else 1
            header = (new_start, new_count)
            hunk_lines = [line]
        elif hunk_lines is not None:
            hunk_lines.append(line)  # inside a hunk, "+++" and "---" are content
        elif line.startswith("+++ "):
            target = line[4:].strip()
            if target == "/dev/null":
                current = old_name  # deletion: key by the old path
            else:
                current = target[2:] if target.startswith("b/") else target
        elif line.startswith("--- "):
            source = line[4:].strip()
            old_name = source[2:] if source.startswith("a/") else None
            current = old_name
    flush()
    return result


def is_python_path(path: str) -> bool:
    return path.endswith(".py") and not any(part in IGNORE_DIRS or part.endswith(".egg-info")
                                            for part in path.split("/"))


class PayloadSource(Source):
    """Base commit plus the head contents of changed files, as one Source."""

    def __init__(self, base: Source, overlay: dict[str, bytes], removed: set[str]) -> None:
        self.base = base
        self.overlay = overlay
        self.removed = removed

    def list_files(self) -> list[str]:
        files = {p for p in self.base.list_files() if p not in self.removed and p not in self.overlay}
        files.update(p for p in self.overlay if is_python_path(p))
        return sorted(files)

    def read(self, path: str) -> bytes:
        if path in self.overlay:
            return self.overlay[path]
        return self.base.read(path)


def changed_python_files(changed_files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [f for f in changed_files if is_python_path(f["path"]) or (f.get("old_path") and is_python_path(f["old_path"]))]


def needs_head_fetch(changed_files: list[dict[str, Any]]) -> bool:
    """True when a changed Python file has no usable head content in the payload."""
    for f in changed_python_files(changed_files):
        if f["status"] == "D" or not is_python_path(f["path"]):
            continue
        if f.get("is_binary") or f.get("head_content") is None:
            return True
    return False


def build_overlay(changed_files: list[dict[str, Any]]) -> tuple[dict[str, bytes], set[str]]:
    overlay: dict[str, bytes] = {}
    removed: set[str] = set()
    for f in changed_files:
        if f["status"] == "D":
            removed.add(f["path"])
            continue
        if f["status"] == "R" and f.get("old_path"):
            removed.add(f["old_path"])
        if is_python_path(f["path"]) and f.get("head_content") is not None and not f.get("is_binary"):
            overlay[f["path"]] = f["head_content"].encode("utf-8")
    return overlay, removed
