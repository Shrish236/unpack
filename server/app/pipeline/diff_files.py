"""File-level diff for the PR page, with every hunk tied to the graph nodes that own it.

`diff_hunks` (per function) was the only diff the API carried, so a change outside a function (imports, module
code, config, docs, a deleted function) had nowhere to show. This keeps every hunk, file by file, and says who
owns it:

- function: the hunk overlaps changed functions (new-side lines), or deleted ones (old-side lines)
- class:    it touches a class body but no function
- module:   it is in a Python file that has a graph container but no changed function covers it
- file:     any other file (non-Python, or a Python file with nothing in the graph)
- none:     there is no patch to show (binary or too large to send)
"""

from __future__ import annotations

from typing import Any

from .payload import Hunk

OWNER_KINDS = ("function", "class", "module", "file", "none")


def _overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_end >= b_start and a_start <= b_end


def _owners(hunk: Hunk, nodes: list[dict[str, Any]], container_ids: set[str], path: str) -> tuple[list[str], str]:
    funcs: list[str] = []
    for n in nodes:
        if n.get("kind") not in ("function", "method") or n.get("start_line") is None:
            continue
        if n["layer"] == "changed" and _overlap(hunk.new_start, hunk.new_end, n["start_line"], n["end_line"]):
            funcs.append(n["id"])
        elif n["layer"] == "ghost" and hunk.removed and _overlap(hunk.old_start, hunk.old_end, n["start_line"], n["end_line"]):
            funcs.append(n["id"])
    if funcs:
        return funcs, "function"
    classes = [
        n for n in nodes
        if n.get("kind") == "class" and n.get("start_line") is not None
        and _overlap(hunk.new_start, hunk.new_end, n["start_line"], n["end_line"])
    ]
    if classes:
        return [max(classes, key=lambda n: n["start_line"])["id"]], "class"  # the innermost class
    if path in container_ids:
        return [path], "module"
    return [], "file"


def build_diff_files(
    changed_files: list[dict[str, Any]], hunks: dict[str, list[Hunk]], graph_nodes: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    """Returns (diff_files, diff_hunks). `diff_hunks` is the per-function view the older clients read."""
    by_path: dict[str, list[dict[str, Any]]] = {}
    for n in graph_nodes:
        by_path.setdefault(n["path"], []).append(n)
    container_ids = {n["id"] for n in graph_nodes if n.get("kind") == "file"}

    meta: dict[str, dict[str, Any]] = {}
    for f in changed_files:
        if isinstance(f.get("path"), str):
            meta[f["path"]] = f
    paths = list(meta) + [p for p in hunks if p not in meta]

    files: list[dict[str, Any]] = []
    per_node: dict[str, list[dict[str, Any]]] = {}
    for path in paths:
        info = meta.get(path, {})
        old_path = info.get("old_path") or None
        nodes = list(by_path.get(path, []))
        if old_path and old_path != path:
            nodes += by_path.get(old_path, [])
        entries: list[dict[str, Any]] = []
        for idx, h in enumerate(hunks.get(path, [])):
            owners, kind = _owners(h, nodes, container_ids, path)
            entry = {
                "id": f"{path}#{idx}", "old_start": h.old_start, "old_end": h.old_end,
                "new_start": h.new_start, "new_end": h.new_end, "added": h.added, "removed": h.removed,
                "patch": h.patch, "owners": owners, "owner_kind": kind,
            }
            entries.append(entry)
            if kind == "function":
                for owner in owners:
                    # The same shape the per-function view always had, plus the hunk id to link back to the file.
                    per_node.setdefault(owner, []).append({
                        "start_line": h.new_start, "end_line": h.new_end, "patch": h.patch, "id": entry["id"],
                    })
        no_patch = bool(info.get("is_binary") or info.get("truncated")) and not entries
        files.append({
            "path": path, "old_path": old_path, "status": info.get("status") or ("D" if hunks.get(path) and hunks[path][0].new_start == 0 else "M"),
            "is_binary": bool(info.get("is_binary")), "truncated": bool(info.get("truncated")),
            "no_patch": no_patch,
            "added": sum(e["added"] for e in entries), "removed": sum(e["removed"] for e in entries),
            "hunks": entries,
        })
    return files, per_node
