"""Function-level change detection between two graphs (server-side, no git checkout needed).

The library's `detect_changes` runs `git diff` on the repository, which fails when the head commit
is not on GitHub yet. This module compares the two graphs directly, with the same classification
rules as the library (`unpack_graph.diff._flags`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from unpack_graph.diff import _flags  # the library's classification rule, shared on purpose


@dataclass
class FuncChange:
    id: str
    kind: str  # added | deleted | modified
    flags: list[str] = field(default_factory=list)  # functional | signature | text_only
    path: str = ""
    qualname: str = ""
    start: int = 0
    end: int = 0
    still_called_by: list[str] = field(default_factory=list)


def compute_changes(base, head) -> list[FuncChange]:
    changes: list[FuncChange] = []
    base_ids, head_ids = set(base.funcs), set(head.funcs)
    for fid in sorted(head_ids - base_ids):
        f = head.funcs[fid]
        changes.append(FuncChange(fid, "added", ["functional"], f.path, f.qualname, f.start, f.end))
    for fid in sorted(base_ids - head_ids):
        f = base.funcs[fid]
        still = sorted({e.src for e in base.in_adj.get(fid, []) if e.src in head.funcs and e.src != fid})
        changes.append(FuncChange(fid, "deleted", [], f.path, f.qualname, f.start, f.end, still))
    for fid in sorted(base_ids & head_ids):
        b, h = base.funcs[fid], head.funcs[fid]
        if b.body_hash == h.body_hash and b.text_hash == h.text_hash:
            continue
        flags = _flags(b, h)
        if not flags:
            continue
        changes.append(FuncChange(fid, "modified", flags, h.path, h.qualname, h.start, h.end))
    return changes
