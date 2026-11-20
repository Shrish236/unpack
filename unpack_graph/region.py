"""In-memory GraphView region builder for diffs."""

from __future__ import annotations

from typing import Any

from .model import ChangeSet, FuncInfo


def build_region(
    changeset: ChangeSet,
    cap: int = 15,
    tests_per_node: int = 5,
) -> dict[str, Any]:
    """Build bounded GraphView JSON around changed functions for UI and AI processing."""
    head_graph = changeset.head_graph
    base_graph = changeset.base_graph

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    # 1. Changed functions
    for fid, ci in changeset.changed_functions.items():
        if ci.kind == "deleted":
            # Ghost node from base graph
            bf: FuncInfo | None = base_graph.functions.get(fid) if base_graph else None
            if bf:
                nodes[fid] = {
                    "id": fid,
                    "type": "Function",
                    "role": "ghost",
                    "ghost": True,
                    "props": {
                        "name": bf.name,
                        "qualname": bf.qualname,
                        "path": bf.path,
                        "start": bf.start,
                        "end": bf.end,
                        "is_async": bf.is_async,
                        "is_method": bf.is_method,
                        "signature": bf.signature,
                        "body_hash": bf.body_hash,
                        "logic_hash": bf.logic_hash,
                        "signature_hash": bf.signature_hash,
                    },
                    "change": {
                        "kind": "deleted",
                        "flags": ci.flags,
                        "head_lines": ci.head_lines,
                        "base_lines": ci.base_lines,
                        "old_id": ci.old_id,
                        "still_called_by": ci.still_called_by,
                    },
                    "tests": None,
                }
            continue

        hf: FuncInfo | None = head_graph.functions.get(fid) if head_graph else None
        if not hf:
            continue

        reach = head_graph.reach_info.get(fid)
        tests_data = None
        if reach:
            tests_data = {
                "label": reach.label,
                "count": reach.count,
                "min_depth": reach.min_depth,
                "path": reach.path,
                "tests": reach.tests[:tests_per_node],
                "unresolved_hint": reach.unresolved_hint,
            }

        nodes[fid] = {
            "id": fid,
            "type": "Function",
            "role": "changed",
            "ghost": False,
            "props": {
                "name": hf.name,
                "qualname": hf.qualname,
                "path": hf.path,
                "start": hf.start,
                "end": hf.end,
                "is_async": hf.is_async,
                "is_method": hf.is_method,
                "signature": hf.signature,
                "body_hash": hf.body_hash,
                "logic_hash": hf.logic_hash,
                "signature_hash": hf.signature_hash,
            },
            "change": {
                "kind": ci.kind,
                "flags": ci.flags,
                "head_lines": ci.head_lines,
                "base_lines": ci.base_lines,
                "old_id": ci.old_id,
                "still_called_by": ci.still_called_by,
            },
            "tests": tests_data,
        }

    # 2. Add 1-hop callers and callees (neighbors) capped at `cap`
    if head_graph:
        for fid in list(nodes.keys()):
            if nodes[fid].get("ghost"):
                continue

            # Callers
            callers = head_graph.calls_by_target.get(fid, [])
            for e in callers[:cap]:
                caller_fn = head_graph.functions.get(e.source)
                if caller_fn and not caller_fn.is_test and e.source not in nodes:
                    nodes[e.source] = {
                        "id": e.source,
                        "type": "Function",
                        "role": "neighbor",
                        "ghost": False,
                        "props": {
                            "name": caller_fn.name,
                            "qualname": caller_fn.qualname,
                            "path": caller_fn.path,
                            "start": caller_fn.start,
                            "end": caller_fn.end,
                            "is_async": caller_fn.is_async,
                            "is_method": caller_fn.is_method,
                            "signature": caller_fn.signature,
                        },
                        "change": None,
                        "tests": None,
                    }

            # Callees
            callees = head_graph.calls_by_source.get(fid, [])
            for e in callees[:cap]:
                callee_fn = head_graph.functions.get(e.target)
                if callee_fn and not callee_fn.is_test and e.target not in nodes:
                    nodes[e.target] = {
                        "id": e.target,
                        "type": "Function",
                        "role": "neighbor",
                        "ghost": False,
                        "props": {
                            "name": callee_fn.name,
                            "qualname": callee_fn.qualname,
                            "path": callee_fn.path,
                            "start": callee_fn.start,
                            "end": callee_fn.end,
                            "is_async": callee_fn.is_async,
                            "is_method": callee_fn.is_method,
                            "signature": callee_fn.signature,
                        },
                        "change": None,
                        "tests": None,
                    }

    # 3. Add Edges between included nodes
    node_set = set(nodes.keys())
    edge_idx = 1
    if head_graph:
        for e in head_graph.edges:
            if e.source in node_set and e.target in node_set:
                edges.append({
                    "id": f"e{edge_idx}",
                    "source": e.source,
                    "target": e.target,
                    "kind": e.kind,
                    "tier": e.tier,
                    "via": e.via,
                    "lines": e.lines,
                    "candidates": e.candidates,
                })
                edge_idx += 1

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "meta": {
            "module_changes": changeset.module_changes,
            "class_changes": {k: v.flags for k, v in changeset.class_changes.items()},
            "unresolved_calls": {},
        },
    }
