"""Change detection and classification between two git revisions or graphs."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .graph import Graph, build_graph
from .model import ChangeItem, ChangeSet
from .source import GitSource


def detect_changes(
    repo_path: str | Path,
    base_rev: str,
    head_rev: str,
    base_graph: Graph | None = None,
    head_graph: Graph | None = None,
) -> ChangeSet:
    """Detect added, deleted, and modified functions between two revisions."""
    repo = Path(repo_path).resolve()

    if base_graph is None:
        base_src = GitSource(repo, base_rev)
        base_graph = build_graph(base_src, reach=False)

    if head_graph is None:
        head_src = GitSource(repo, head_rev)
        head_graph = build_graph(head_src, reach=True)

    cs = ChangeSet(base_rev=base_rev, head_rev=head_rev, base_graph=base_graph, head_graph=head_graph)

    # Find modified, added, deleted files via git diff --name-status
    try:
        cmd = ["git", "-C", str(repo), "diff", "--name-status", "-M", base_rev, head_rev]
        p = subprocess.run(cmd, capture_output=True, text=True, check=True)
        for line in p.stdout.splitlines():
            parts = line.strip().split("\t")
            if not parts:
                continue
            status = parts[0][0]
            if status == "A":
                cs.added_files.append(parts[1])
            elif status == "M":
                cs.modified_files.append(parts[1])
            elif status == "D":
                cs.deleted_files.append(parts[1])
            elif status == "R":
                cs.renamed_files.append((parts[1], parts[2]))
    except Exception:
        # Fallback if git command unavailable or working tree diff
        pass

    base_fids = set(base_graph.functions.keys())
    head_fids = set(head_graph.functions.keys())

    # Added functions
    for fid in head_fids - base_fids:
        hf = head_graph.functions[fid]
        ci = ChangeItem(
            id=fid,
            kind="added",
            flags=["functional"],
            head_lines=[[hf.start, hf.end]],
        )
        cs.changed_functions[fid] = ci

    # Deleted functions
    for fid in base_fids - head_fids:
        bf = base_graph.functions[fid]
        # Check still_called_by in head
        still_called = []
        for e in head_graph.edges:
            if e.kind == "CALLS" and (e.target == fid or e.raw == bf.name):
                still_called.append(e.source)

        ci = ChangeItem(
            id=fid,
            kind="deleted",
            flags=[],
            base_lines=[[bf.start, bf.end]],
            still_called_by=list(set(still_called)),
        )
        cs.changed_functions[fid] = ci

    # Modified functions
    for fid in base_fids & head_fids:
        bf = base_graph.functions[fid]
        hf = head_graph.functions[fid]

        if bf.body_hash != hf.body_hash:
            flags = []
            if bf.signature_hash != hf.signature_hash:
                flags.append("signature")
            if bf.logic_hash != hf.logic_hash:
                flags.append("functional")
            if not flags:
                flags.append("text_only")

            ci = ChangeItem(
                id=fid,
                kind="modified",
                flags=flags,
                head_lines=[[hf.start, hf.end]],
                base_lines=[[bf.start, bf.end]],
            )
            cs.changed_functions[fid] = ci

    return cs
