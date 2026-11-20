"""Region query: changed functions + one hop of CALLS + parents + reaching tests -> GraphView JSON.

This is the in-memory reference implementation.  neo4j_io.region_query() runs the same logic as a
single Cypher query and must return an equal GraphView (checked by tests/test_neo4j.py).
"""
from __future__ import annotations

from typing import Optional

from .diff import ChangeSet
from .graph import Graph
from .model import TIER_RANK
from .reach import path_of

VERSION = "1.0"
# internal role -> role allowed by schemas/graphview.schema.json
CONTRACT_ROLE = {
    "changed": "changed", "caller": "neighbor", "callee": "neighbor", "overridden": "neighbor",
    "overrider": "neighbor", "parent_class": "container", "base_class": "container",
    "ghost": "ghost", "test": "test",
}
DEFAULT_CAP = 15
DEFAULT_TESTS_PER_NODE = 5


def func_props(f) -> dict:
    return {
        "id": f.id, "name": f.name, "qualname": f.qualname, "path": f.path, "start": f.start, "end": f.end,
        "is_async": f.is_async, "is_method": f.is_method, "is_test": f.is_test, "is_fixture": f.is_fixture,
        "is_abstract": f.is_abstract, "is_property": f.is_property, "decorators": list(f.decorators),
        "signature": f.signature, "doc": f.doc, "body_hash": f.body_hash, "logic_hash": f.logic_hash,
        "signature_hash": f.signature_hash,
    }


def to_contract(node_list: list, edge_list: list) -> None:
    """Shape nodes and edges as schemas/graphview.schema.json requires, in place.

    Internal roles are finer than the contract's, so the internal role is kept as `relation`.
    Every edge gets a stable `id`. Shared by the in-memory and the Neo4j region paths so that
    both produce identical output.
    """
    for n in node_list:
        n["relation"] = n["role"]
        n["role"] = CONTRACT_ROLE[n["role"]]
    for e in edge_list:
        e["id"] = f'{e["kind"]}:{e["source"]}->{e["target"]}'


def class_props(c) -> dict:
    return {"id": c.id, "name": c.name, "qualname": c.qualname, "path": c.path, "start": c.start,
            "end": c.end, "bases_raw": list(c.bases_raw), "bases": list(c.bases_raw)}


def _tests_info(g: Graph, fid: str, tests_per_node: int, with_tests: bool = True,
                changed_paths: frozenset = frozenset()) -> Optional[dict]:
    ri = g.reach.get(fid)
    if ri is None:
        return None
    if ri.label == "reached_uncertain":
        pairs = g.reach_pairs_loose
        count, depth, path = ri.uncertain_count, ri.uncertain_depth, ri.uncertain_path
    else:
        pairs = g.reach_pairs
        count, depth, path = ri.count, ri.min_depth, ri.path
    out = {"label": ri.label, "count": count, "min_depth": depth, "path": list(path), "tests": [],
           "unresolved_hint": ri.unresolved_hint}
    if with_tests and ri.label in ("direct", "reached", "reached_uncertain"):
        ts = []
        for tid, seen in pairs.items():
            ent = seen.get(fid)
            if ent is not None and ent[0] > 0 and tid != fid:
                # tests in files touched by the change first, then nearest, then id
                ts.append((0 if tid.split("::")[0] in changed_paths else 1, ent[0], tid))
        ts.sort()
        out["tests"] = [{"id": t, "depth": d} for _c, d, t in ts[:tests_per_node]]
    return out


def _edge(e, src=None, dst=None) -> dict:
    return {"source": src or e.src, "target": dst or e.dst, "kind": "CALLS", "tier": e.tier, "via": e.via,
            "line": e.line, "lines": list(e.lines), "count": e.count, "raw": e.raw,
            "candidates": list(e.candidates)}


def build_meta(cs: ChangeSet, changed_funcs: list, cap: int, tests_per_node: int) -> dict:
    """Region metadata. The `module_changes`, `class_changes` and `unresolved_calls` members are
    objects keyed by path, class id and function id, as the GraphView schema requires."""
    g = cs.head_graph
    module_changes = {
        m["path"]: {k: v for k, v in m.items() if k != "path"}
        for m in cs.modules if m.get("module_level_changed")
    }
    class_changes = {}
    for k in cs.classes:
        class_changes[k["id"]] = {f: v for f, v in k.items() if f != "id"}
    unresolved = {
        fid: [{"line": ln, "raw": raw, "reason": why} for ln, raw, why in g.unresolved.get(fid, [])]
        for fid in changed_funcs if g.unresolved.get(fid)
    }
    return {
        "version": VERSION, "base": cs.base, "head": cs.head, "cap": cap, "tests_per_node": tests_per_node,
        "changed_count": len(changed_funcs),
        "module_changes": module_changes,
        "class_changes": class_changes,
        "unresolved_calls": unresolved,
    }


def build_region(cs: ChangeSet, cap: int = DEFAULT_CAP, tests_per_node: int = DEFAULT_TESTS_PER_NODE) -> dict:
    g, gb = cs.head_graph, cs.base_graph
    changed_paths = frozenset(np_ for _st, _op, np_ in cs.files)
    nodes: dict = {}
    edges: dict = {}
    changed_ids = []

    def add_func_node(fid: str, role: str, graph: Graph = g, change=None, ghost=False):
        if fid in nodes:
            if role == "changed" or (nodes[fid]["role"] in ("caller", "callee") and role == "changed"):
                nodes[fid]["role"] = role
            return
        f = graph.funcs[fid]
        nodes[fid] = {"id": fid, "type": "Function", "role": role, "ghost": ghost,
                      "props": func_props(f), "change": change,
                      "tests": None if ghost else _tests_info(g, fid, tests_per_node, with_tests=False)}

    def add_class_node(cid: str, role: str):
        if cid in nodes:
            return
        c = g.classes.get(cid)
        if c is None:
            return
        nodes[cid] = {"id": cid, "type": "Class", "role": role, "ghost": False, "props": class_props(c),
                      "change": None, "tests": None}

    def add_edge(d: dict):
        edges[(d["source"], d["target"], d["kind"])] = d

    changed_funcs = []
    for c in cs.functions:
        cd = {"kind": c.kind, "flags": list(c.flags), "head_lines": c.head_lines,
              "base_lines": c.base_lines, "old_id": c.old_id, "still_called_by": list(c.still_called_by)}
        if c.kind == "deleted":
            add_func_node(c.id, "ghost", gb, cd, ghost=True)
            cand = []
            for caller in c.still_called_by:
                if caller in g.funcs and not g.mods[g.funcs[caller].path].is_test:
                    be = gb.calls.get((caller, c.id))
                    if be is not None:
                        cand.append((TIER_RANK[be.tier], -(g.reach[caller].count if caller in g.reach else 0), caller, be))
            cand.sort(key=lambda x: x[:3])
            for _r, _t, caller, be in cand[:cap]:
                add_func_node(caller, "caller")
                add_edge({"source": caller, "target": c.id, "kind": "CALLS", "tier": be.tier, "via": "removed",
                          "line": be.line, "lines": list(be.lines), "count": be.count, "raw": be.raw,
                          "candidates": []})
            continue
        if c.id not in g.funcs:
            continue
        add_func_node(c.id, "changed", g, cd)
        nodes[c.id]["tests"] = _tests_info(g, c.id, tests_per_node, with_tests=True, changed_paths=changed_paths)
        changed_funcs.append(c.id)
        changed_ids.append(c.id)

    def rank(e, other: str):
        ri = g.reach.get(other)
        return (TIER_RANK[e.tier], -(ri.count if ri else 0), other)

    for fid in changed_funcs:
        f = g.funcs[fid]
        # callers / callees (production code only; tests are attached as `tests`)
        callers = [e for e in g.in_adj.get(fid, []) if "::" in e.src and e.src != fid
                   and not g.mods[g.funcs[e.src].path].is_test]
        callees = [e for e in g.out_adj.get(fid, []) if e.dst != fid and not g.mods[g.funcs[e.dst].path].is_test]
        for e in sorted(callers, key=lambda e: rank(e, e.src))[:cap]:
            add_func_node(e.src, "caller")
            add_edge(_edge(e))
        for e in sorted(callees, key=lambda e: rank(e, e.dst))[:cap]:
            add_func_node(e.dst, "callee")
            add_edge(_edge(e))
        # parents
        if f.class_id:
            add_class_node(f.class_id, "parent_class")
            add_edge({"source": f.class_id, "target": fid, "kind": "HAS_METHOD", "tier": "EXTRACTED",
                      "via": None, "line": 0, "lines": [], "count": 0, "raw": "", "candidates": []})
            for child, parent in g.inherits:
                if child == f.class_id:
                    add_class_node(parent, "base_class")
                    add_edge({"source": child, "target": parent, "kind": "INHERITS", "tier": "EXTRACTED",
                              "via": None, "line": 0, "lines": [], "count": 0, "raw": "", "candidates": []})
        for m, o in g.overrides:
            if m == fid:
                add_func_node(o, "overridden")
                add_edge({"source": m, "target": o, "kind": "OVERRIDES", "tier": "EXTRACTED", "via": None,
                          "line": 0, "lines": [], "count": 0, "raw": "", "candidates": []})
            elif o == fid:
                add_func_node(m, "overrider")
                add_edge({"source": m, "target": o, "kind": "OVERRIDES", "tier": "EXTRACTED", "via": None,
                          "line": 0, "lines": [], "count": 0, "raw": "", "candidates": []})
        # reaching tests
        ti = nodes[fid]["tests"]
        if ti:
            uncertain = ti["label"] == "reached_uncertain"
            pairs = g.reach_pairs_loose if uncertain else g.reach_pairs
            for t in ti["tests"]:
                tid = t["id"]
                if tid not in nodes:
                    add_func_node(tid, "test")
                add_edge({"source": tid, "target": fid, "kind": "REACHES", "tier": "AMBIGUOUS" if uncertain else "INFERRED",
                          "via": None, "line": 0, "lines": [], "count": 0, "raw": "", "candidates": [],
                          "depth": t["depth"], "path": path_of(pairs[tid], fid)})
    node_list = sorted(nodes.values(), key=lambda n: (n["role"] != "changed", n["role"], n["id"]))
    edge_list = sorted(edges.values(), key=lambda e: (e["kind"], e["source"], e["target"]))
    to_contract(node_list, edge_list)

    meta = build_meta(cs, changed_funcs, cap, tests_per_node)
    return {"version": VERSION, "meta": meta, "nodes": node_list, "edges": edge_list}
