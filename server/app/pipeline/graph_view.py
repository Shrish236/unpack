"""Adapts the code graph library's change set to the API contract (server design §5.5, §6).

Everything here is facts from code: changed functions, neighbours, tests, impact and reading
order. Reasons and session review are not built in this version (see llm/placeholder.py).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from ..config import settings
from .payload import Hunk

TIER_RANK = {"EXTRACTED": 0, "INFERRED": 1, "AMBIGUOUS": 2}


class InvalidGraphView(Exception):
    pass


@dataclass
class GraphBuild:
    graph: dict[str, Any]  # {nodes, edges, collapsed, truncated}
    reading_order: list[str]
    impact: dict[str, Any]  # {summary, by_node}
    diff_hunks: dict[str, list[dict[str, Any]]]
    stats: dict[str, Any]
    not_reached: list[str]  # display names of changed functions with no test
    changed_ids: list[str] = field(default_factory=list)


def _is_public(name: str) -> bool:
    return not name.startswith("_")


def _change_kind(ci: Any) -> str:
    if ci.kind == "added":
        return "added"
    if ci.kind == "deleted":
        return "deleted"
    flags = set(ci.flags)
    if "signature" in flags:
        return "signature"
    if "functional" in flags:
        return "functional"
    return "text_only"


def _class_id(func: Any) -> str | None:
    if not func.is_method or "." not in func.qualname:
        return None
    class_qual = func.qualname.rsplit(".", 1)[0]
    return f"{func.path}::{class_qual}"


def _label_of(func: Any) -> str:
    return func.qualname


def _nearest_tested(head: Any, fid: str, max_depth: int = 3) -> str | None:
    """Closest function (by calls, either direction) that a test reaches."""
    seen = {fid}
    queue: deque[tuple[str, int]] = deque([(fid, 0)])
    while queue:
        current, depth = queue.popleft()
        if depth >= max_depth:
            continue
        neighbours = [e.target for e in head.calls_by_source.get(current, [])]
        neighbours += [e.source for e in head.calls_by_target.get(current, [])]
        for nxt in neighbours:
            if nxt in seen or nxt not in head.functions:
                continue
            seen.add(nxt)
            info = head.reach_info.get(nxt)
            if info and info.label in ("direct", "reached"):
                return nxt
            queue.append((nxt, depth + 1))
    return None


def _impact(head: Any, anchors: list[str], depth_limit: int) -> dict[str, Any]:
    by_node: dict[str, list[dict[str, Any]]] = {}
    all_hit: set[str] = set()
    uncertain_total = 0
    for anchor in anchors:
        best: dict[str, tuple[int, int, bool]] = {}  # id -> (depth, tier rank, uncertain)
        queue: deque[tuple[str, int, int]] = deque([(anchor, 0, 0)])
        visited = {anchor}
        while queue:
            current, depth, worst = queue.popleft()
            if depth >= depth_limit:
                continue
            for edge in head.calls_by_target.get(current, []):
                caller = edge.source
                if caller in visited or caller not in head.functions or head.functions[caller].is_test:
                    continue
                visited.add(caller)
                tier = edge.tier or "EXTRACTED"
                rank = max(worst, TIER_RANK.get(tier, 0))
                best[caller] = (depth + 1, rank, rank > 0)
                queue.append((caller, depth + 1, rank))
        hops = []
        for hop_id, (depth, rank, uncertain) in sorted(best.items(), key=lambda kv: (kv[1][0], kv[0])):
            tier = {v: k for k, v in TIER_RANK.items()}[rank]
            hops.append({"id": hop_id, "depth": depth, "tier": tier, "uncertain": uncertain})
            all_hit.add(hop_id)
            uncertain_total += 1 if uncertain else 0
        by_node[anchor] = hops
    return {"by_node": by_node, "all_hit": all_hit, "uncertain": uncertain_total}


def _reading_order(live_ids: list[str], ghost_ids: list[str], calls: dict[str, set[str]],
                   key_of: dict[str, tuple[str, int]]) -> list[str]:
    """Callers before callees (topological), ties by path then line. Deleted functions last."""
    ids = set(live_ids)
    indeg = {i: 0 for i in ids}
    for caller in ids:
        for callee in calls.get(caller, set()):
            if callee in ids and callee != caller:
                indeg[callee] += 1
    order: list[str] = []
    remaining = set(ids)
    while remaining:
        ready = sorted((i for i in remaining if indeg[i] == 0), key=lambda i: key_of[i])
        pick = ready[0] if ready else min(remaining, key=lambda i: key_of[i])  # cycle: break by path, line
        order.append(pick)
        remaining.discard(pick)
        for callee in calls.get(pick, set()):
            if callee in remaining:
                indeg[callee] = max(0, indeg[callee] - 1)
    return order + sorted(ghost_ids, key=lambda i: key_of.get(i, ("", 0)))


def _hunks_for(fid: str, path: str, start: int, end: int, hunks: dict[str, list[Hunk]]) -> list[dict[str, Any]]:
    out = []
    for hunk in hunks.get(path, []):
        if hunk.new_end >= start and hunk.new_start <= end:
            out.append({"start_line": hunk.new_start, "end_line": hunk.new_end, "patch": hunk.patch})
    return out


def build_graph_view(
    cs: Any,
    base: Any,
    head: Any,
    diff_hunks: dict[str, list[Hunk]],
) -> GraphBuild:
    max_nodes = settings.MAX_GRAPH_NODES
    max_edges = settings.MAX_GRAPH_EDGES
    per_node = settings.MAX_NEIGHBORS_PER_NODE

    changed = list(cs.changed_functions.values())
    changed_ids = [c.id for c in changed]
    live_ids = [c.id for c in changed if c.kind != "deleted" and c.id in head.functions]

    nodes: dict[str, dict[str, Any]] = {}
    containers: dict[str, dict[str, Any]] = {}
    required: set[str] = set()
    origin: dict[str, tuple[str, str]] = {}  # neighbour id -> (anchor, direction), for collapsing
    collapsed: dict[tuple[str, str, str], list[str]] = {}
    edges_omitted = 0

    def add_file(path: str, source_graph: Any) -> None:
        if path in containers:
            return
        mod = source_graph.modules.get(path)
        containers[path] = {
            "id": path, "label": path, "kind": "file", "parent": None, "path": path,
            "layer": "container", "imports": [], "imports_total": len(mod.imports) if mod else 0,
        }

    def add_class(func: Any, source_graph: Any) -> str | None:
        cid = _class_id(func)
        if cid is None:
            return None
        if cid not in containers:
            cls = next((c for c in source_graph.classes.values() if c.id == cid), None)
            add_file(func.path, source_graph)
            containers[cid] = {
                "id": cid, "label": cid.split("::", 1)[1].rsplit(".", 1)[-1], "kind": "class",
                "parent": func.path, "path": func.path, "layer": "container",
                "start_line": cls.start if cls else func.start,
                "end_line": cls.end if cls else func.end,
                "bases": list(cls.bases_raw) if cls else [],
            }
        return cid

    def base_node(func: Any, fid: str, layer: str, change: dict[str, Any] | None, test: dict[str, Any] | None,
                  callers: int, callees: int, parent: str) -> dict[str, Any]:
        return {
            "id": fid, "label": _label_of(func), "kind": "method" if func.is_method else "function",
            "parent": parent, "path": func.path, "layer": layer,
            "start_line": func.start, "end_line": func.end, "signature": func.signature,
            "is_async": func.is_async, "is_public": _is_public(func.name), "bases": [],
            "change": change, "test": test, "callers_count": callers, "callees_count": callees,
            "is_test": func.is_test, "has_reason": False, "finding_ids": [],
        }

    # 1. Changed and ghost nodes are always included.
    for c in changed:
        change = {"kind": _change_kind(c), "source": "outside_session"}
        if c.kind == "deleted":
            func = base.functions.get(c.id)
            if func is None:
                continue
            add_file(func.path, base)
            nodes[c.id] = base_node(func, c.id, "ghost", change, None,
                                    len(c.still_called_by), 0, func.path)
        else:
            func = head.functions.get(c.id)
            if func is None:
                continue
            add_file(func.path, head)
            parent = add_class(func, head) or func.path
            reach = head.reach_info.get(c.id)
            if reach and reach.label in ("direct", "reached", "reached_uncertain"):
                test = {"label": reach.label, "count": reach.count,
                        "shortest_path": list(reach.path), "nearest_tested": None}
            else:
                test = {"label": "none", "count": 0, "shortest_path": [],
                        "nearest_tested": _nearest_tested(head, c.id)}
            nodes[c.id] = base_node(func, c.id, "changed", change, test,
                                    len(head.calls_by_target.get(c.id, [])),
                                    len(head.calls_by_source.get(c.id, [])), parent)
        required.add(c.id)

    # 2. Test paths: the test node and every node on its shortest path (never cut).
    for c in changed:
        node = nodes.get(c.id)
        if not node or node["layer"] != "changed" or not node["test"]:
            continue
        for pid in node["test"]["shortest_path"]:
            if pid in nodes or pid not in head.functions:
                continue
            func = head.functions[pid]
            add_file(func.path, head)
            parent = add_class(func, head) or func.path
            layer = "test" if func.is_test else "neighbor"
            nodes[pid] = base_node(func, pid, layer, None, None,
                                   len(head.calls_by_target.get(pid, [])),
                                   len(head.calls_by_source.get(pid, [])), parent)
            required.add(pid)

    # 3. Neighbours: one hop callers and callees, capped per node. Overflow is collapsed by file.
    budget = max_nodes - len(required)
    for fid in live_ids:
        for direction, edges in (("callers", head.calls_by_target.get(fid, [])),
                                 ("callees", head.calls_by_source.get(fid, []))):
            shown = 0
            seen: set[str] = set()
            for edge in edges:
                other = edge.source if direction == "callers" else edge.target
                if other in seen or other == fid or other not in head.functions:
                    continue
                func = head.functions[other]
                if func.is_test:
                    continue
                seen.add(other)
                if other in nodes:
                    continue
                if shown < per_node and budget > 0:
                    add_file(func.path, head)
                    parent = add_class(func, head) or func.path
                    nodes[other] = base_node(func, other, "neighbor", None, None,
                                             len(head.calls_by_target.get(other, [])),
                                             len(head.calls_by_source.get(other, [])), parent)
                    origin[other] = (fid, direction)
                    shown += 1
                    budget -= 1
                else:
                    collapsed.setdefault((fid, direction, func.path), []).append(other)

    # 4. Impact: callers up to IMPACT_DEPTH, with the tier of the weakest edge on the path.
    impact_raw = _impact(head, live_ids, settings.IMPACT_DEPTH)

    # 5. Node cap: drop neighbours that are not required; their ids move into collapsed groups.
    non_container = [nid for nid, n in nodes.items() if n["layer"] != "container"]
    nodes_omitted = 0
    if len(non_container) > max_nodes:
        droppable = [nid for nid in non_container if nid not in required and nid in origin]
        for nid in droppable[: len(non_container) - max_nodes]:
            anchor, direction = origin[nid]
            func = head.functions[nid]
            nodes.pop(nid)
            collapsed.setdefault((anchor, direction, func.path), []).append(nid)
            nodes_omitted += 1

    # 6. Impact hops that are not nodes must be in a collapsed group of their anchor.
    for anchor, hops in impact_raw["by_node"].items():
        for hop in hops:
            hid = hop["id"]
            if hid in nodes:
                continue
            if any(hid in ids for (a, _d, _p), ids in collapsed.items() if a == anchor):
                continue
            func = head.functions[hid]
            collapsed.setdefault((anchor, "callers", func.path), []).append(hid)

    # 7. Edges between included nodes (CALLS) and test REACHES edges, capped.
    edge_list: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str, str]] = set()
    node_ids = set(nodes)
    ordered = sorted(
        (e for e in head.edges if e.kind == "CALLS" and e.tier in ("EXTRACTED", "INFERRED", "AMBIGUOUS")),
        key=lambda e: 0 if (e.source in required or e.target in required) else 1,
    )
    for e in ordered:
        if e.source not in node_ids or e.target not in node_ids:
            continue
        key = (e.source, e.target, "CALLS")
        if key in seen_edges:
            continue
        if len(edge_list) >= max_edges:
            edges_omitted += 1
            continue
        seen_edges.add(key)
        edge_list.append({"id": f"e{len(edge_list) + 1}", "source": e.source, "target": e.target,
                          "kind": "CALLS", "tier": e.tier, "via": e.via})
    for c in changed:
        node = nodes.get(c.id)
        if not node or node["layer"] != "changed" or not node["test"]:
            continue
        path_ids = node["test"]["shortest_path"]
        if len(path_ids) >= 2 and path_ids[0] in node_ids:
            key = (path_ids[0], c.id, "REACHES")
            if key not in seen_edges and len(edge_list) < max_edges:
                seen_edges.add(key)
                edge_list.append({"id": f"e{len(edge_list) + 1}", "source": path_ids[0], "target": c.id,
                                  "kind": "REACHES", "tier": "EXTRACTED", "via": None})

    # 8. Containers join the node list, with their parent chain.
    for cid, container in containers.items():
        nodes.setdefault(cid, container)
    for n in list(nodes.values()):
        parent = n.get("parent")
        if parent and parent not in nodes and parent in containers:
            nodes[parent] = containers[parent]

    collapsed_list = []
    hidden: set[str] = set()
    for idx, ((anchor, direction, path), ids) in enumerate(collapsed.items(), start=1):
        ids = sorted(set(i for i in ids if i not in nodes))
        if not ids:
            continue
        hidden.update(ids)
        collapsed_list.append({"id": f"c{idx}", "anchor": anchor, "direction": direction,
                               "file": path, "count": len(ids), "node_ids": ids})

    by_node = {a: [h for h in hops if h["id"] in nodes or h["id"] in hidden]
               for a, hops in impact_raw["by_node"].items()}
    by_node = {a: h for a, h in by_node.items() if h}
    hit_ids = impact_raw["all_hit"]
    hit_files = {head.functions[i].path for i in hit_ids if i in head.functions}
    public_api = sum(1 for fid in hit_ids | set(live_ids)
                     if fid in head.functions and _is_public(head.functions[fid].name))
    impact = {
        "summary": {
            "functions": len(hit_ids),
            "files": len(hit_files),
            "public_api": public_api,
            "uncertain_paths": impact_raw["uncertain"],
        },
        "by_node": by_node,
    }

    key_of = {nid: (n["path"], n["start_line"]) for nid, n in nodes.items() if "start_line" in n}
    ghost_ids = [c.id for c in changed if c.kind == "deleted" and c.id in nodes]
    reading = _reading_order(
        [i for i in live_ids if i in nodes],
        ghost_ids,
        {fid: {e.target for e in head.calls_by_source.get(fid, [])} for fid in live_ids},
        key_of,
    )

    hunks_out: dict[str, list[dict[str, Any]]] = {}
    for c in changed:
        node = nodes.get(c.id)
        if node and node["layer"] == "changed":
            found = _hunks_for(c.id, node["path"], node["start_line"], node["end_line"], diff_hunks)
            if found:
                hunks_out[c.id] = found

    not_reached_nodes = [n for n in nodes.values() if n["layer"] == "changed" and n["test"]["label"] == "none"]
    not_reached = [f"{n['path']}::{n['label']}"
                   for n in sorted(not_reached_nodes, key=lambda n: (n["path"], n["start_line"]))]

    by_change: dict[str, int] = {"added": 0, "functional": 0, "signature": 0, "text_only": 0, "deleted": 0}
    for c in changed:
        by_change[_change_kind(c)] += 1
    stats = {
        "functions_changed": len(changed),
        "by_source": {"session": 0, "session_then_formatted": 0, "session_partial": 0,
                      "outside_session": len(changed)},
        "by_change": by_change,
        "not_reached_by_tests": len(not_reached),
    }

    graph = {
        "nodes": list(nodes.values()),
        "edges": edge_list,
        "collapsed": collapsed_list,
        "truncated": {"nodes_omitted": nodes_omitted, "edges_omitted": edges_omitted},
    }
    return GraphBuild(
        graph=graph,
        reading_order=reading,
        impact=impact,
        diff_hunks=hunks_out,
        stats=stats,
        not_reached=not_reached,
        changed_ids=changed_ids,
    )


def validate_graph_view(build: GraphBuild, max_nodes: int, max_edges: int) -> None:
    """Server design §5.5 guarantees. A violation fails the analysis; bad data is never stored."""
    nodes = build.graph["nodes"]
    ids = [n["id"] for n in nodes]
    if len(ids) != len(set(ids)):
        raise InvalidGraphView("node ids are not unique")
    node_ids = set(ids)
    for e in build.graph["edges"]:
        if e["source"] not in node_ids or e["target"] not in node_ids:
            raise InvalidGraphView(f"edge {e['id']} points outside the graph")
    for n in nodes:
        if n.get("parent") and n["parent"] not in node_ids:
            raise InvalidGraphView(f"node {n['id']} has a missing parent")
    for rid in build.reading_order:
        if rid not in node_ids:
            raise InvalidGraphView(f"reading order id {rid} is not a node")
    for anchor in build.impact["by_node"]:
        if anchor not in node_ids:
            raise InvalidGraphView(f"impact anchor {anchor} is not a node")
    collapsed_ids = {i for g in build.graph["collapsed"] for i in g["node_ids"]}
    for anchor, hops in build.impact["by_node"].items():
        for hop in hops:
            if hop["id"] not in node_ids and hop["id"] not in collapsed_ids:
                raise InvalidGraphView(f"impact id {hop['id']} is neither a node nor collapsed")
    for g in build.graph["collapsed"]:
        if g["anchor"] not in node_ids:
            raise InvalidGraphView(f"collapsed anchor {g['anchor']} is not a node")
    for c in build.changed_ids:
        if c not in node_ids:
            raise InvalidGraphView(f"changed function {c} is not a node")
    non_container = [n for n in nodes if n["layer"] != "container"]
    if len(non_container) > max_nodes:
        raise InvalidGraphView("too many nodes")
    if len(build.graph["edges"]) > max_edges:
        raise InvalidGraphView("too many edges")
