"""Graph container and builder for the code knowledge graph."""

from __future__ import annotations

from typing import Any

from .extract import extract_file
from .model import (
    ClassInfo,
    Edge,
    FuncInfo,
    ModuleInfo,
    ReachInfo,
)
from .resolve import Resolver
from .source import Source


class Graph:
    """In-memory property graph representation of the codebase."""

    def __init__(self) -> None:
        self.modules: dict[str, ModuleInfo] = {}
        self.classes: dict[str, ClassInfo] = {}
        self.functions: dict[str, FuncInfo] = {}
        self.edges: list[Edge] = []
        self.calls_by_source: dict[str, list[Edge]] = {}
        self.calls_by_target: dict[str, list[Edge]] = {}
        self.reach_info: dict[str, ReachInfo] = {}

    def add_edge(self, edge: Edge) -> None:
        self.edges.append(edge)
        if edge.kind == "CALLS":
            self.calls_by_source.setdefault(edge.source, []).append(edge)
            self.calls_by_target.setdefault(edge.target, []).append(edge)


def build_graph(
    source: Source,
    resolver_opts: dict[str, Any] | None = None,
    reach: bool = True,
) -> Graph:
    """Extract, resolve, and assemble whole-repo code knowledge graph."""
    g = Graph()
    files = source.list_files()

    # Pass 1: Extract every file independently
    for path in files:
        data = source.read(path)
        mod_info = extract_file(path, data)
        g.modules[mod_info.path] = mod_info
        for c in mod_info.classes:
            g.classes[c.id] = c
        for f in mod_info.defs:
            g.functions[f.id] = f

    # Pass 2: Symbol and Call Resolution
    resolver = Resolver(g.modules, opts=resolver_opts)
    resolved_sites = resolver.resolve_all()

    # Aggregate CALLS edges
    edge_map: dict[tuple[str, str], Edge] = {}
    for site in resolved_sites:
        for target_id, tier, via in site.targets:
            key = (site.owner, target_id)
            if key in edge_map:
                existing = edge_map[key]
                existing.count += 1
                if site.line not in existing.lines:
                    existing.lines.append(site.line)
            else:
                e = Edge(
                    source=site.owner,
                    target=target_id,
                    kind="CALLS",
                    tier=tier,
                    via=via,
                    lines=[site.line] if site.line else [],
                    candidates=site.candidates,
                    raw=site.raw,
                )
                edge_map[key] = e

    for edge in edge_map.values():
        g.add_edge(edge)

    # Add Structural Edges: HAS_METHOD, INHERITS, OVERRIDES
    for c in g.classes.values():
        for base in c.bases_raw:
            # Match base class in repo
            for other_c in g.classes.values():
                if other_c.name == base:
                    g.add_edge(Edge(source=c.id, target=other_c.id, kind="INHERITS"))

    for f in g.functions.values():
        if f.is_method:
            parent_cid = f.id.rsplit(".", 1)[0].replace("#setter", "")
            if parent_cid in g.classes:
                g.add_edge(Edge(source=parent_cid, target=f.id, kind="HAS_METHOD"))

    # Compute Reachability
    if reach:
        from .reach import compute_reach
        g.reach_info = compute_reach(g)

    return g
