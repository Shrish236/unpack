"""Reading flow of a change: in what order, and in which groups, a reviewer should read the changed functions.

Two flows are stored and the UI lets the reader choose:

- deterministic: callers before callees over the CALLS edges between changed functions, grouped by the call
  chains they form. Computed from the code graph alone, so it exists for every push.
- llm: stages with a title and a note, written by the model from the verified reasons (see llm/flow.py).
  It can be missing (no session, quota, model failure). The deterministic flow is then the only one.

Both flows list every changed node exactly once. A flow that dropped a node would hide code from a reviewer.
"""

from __future__ import annotations

from typing import Any

FLOW_VERSION = 1


def _components(ids: list[str], edges: list[tuple[str, str]]) -> list[list[str]]:
    """Connected components (undirected) of the changed functions, each in the order of `ids`."""
    parent = {i: i for i in ids}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        if a in parent and b in parent:
            parent[find(a)] = find(b)
    groups: dict[str, list[str]] = {}
    for i in ids:
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())  # dicts keep insertion order: components are ordered by their first member


def deterministic_flow(graph: dict[str, Any], reading_order: list[str]) -> dict[str, Any]:
    """Stages over the changed (live) functions in `reading_order`, then one stage for deleted functions."""
    nodes = {n["id"]: n for n in graph["nodes"]}
    live = [i for i in reading_order if i in nodes and nodes[i]["layer"] == "changed"]
    ghosts = [i for i in reading_order if i in nodes and nodes[i]["layer"] == "ghost"]
    # Anything changed but missing from the reading order is still listed (it would be a bug upstream, not a reason to hide code).
    seen = set(live) | set(ghosts)
    live += sorted((i for i, n in nodes.items() if n["layer"] == "changed" and i not in seen),
                   key=lambda i: (nodes[i]["path"], nodes[i].get("start_line") or 0))

    calls = [(e["source"], e["target"]) for e in graph["edges"] if e["kind"] == "CALLS"]
    called_by_changed = {b for a, b in calls if a in set(live) and b in set(live)}
    stages: list[dict[str, Any]] = []
    singles: dict[str, list[str]] = {}
    for comp in _components(live, calls):
        if len(comp) == 1:
            singles.setdefault(nodes[comp[0]]["path"], []).append(comp[0])
            continue
        roots = [i for i in comp if i not in called_by_changed] or comp[:1]
        entry = nodes[roots[0]]["label"]
        stages.append({
            "title": f"Starts at {entry}", "summary": f"{len(comp)} functions that call each other",
            "node_ids": comp, "first": live.index(comp[0]),
        })
    for path, comp in singles.items():
        stages.append({
            "title": f"Changes in {path}", "summary": "Not connected to the other changed functions by a call",
            "node_ids": comp, "first": live.index(comp[0]),
        })
    stages.sort(key=lambda s: s.pop("first"))
    if ghosts:
        stages.append({"title": "Removed", "summary": "Functions deleted by this change", "node_ids": ghosts})
    order = [i for s in stages for i in s["node_ids"]]
    return {"mode": "deterministic", "stages": stages, "order": order}


def build_flow(graph: dict[str, Any], reading_order: list[str], llm: dict[str, Any] | None = None,
               model: str | None = None, prompt_version: int | None = None, warnings: list[str] | None = None) -> dict[str, Any]:
    return {
        "version": FLOW_VERSION,
        "deterministic": deterministic_flow(graph, reading_order),
        "llm": llm,
        "model": model,
        "prompt_version": prompt_version,
        "warnings": warnings or [],
    }
