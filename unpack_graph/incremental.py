"""Incremental graph update: re-extract changed files and re-resolve affected closure."""

from __future__ import annotations

from .extract import extract_file
from .graph import Graph
from .reach import compute_reach
from .resolve import Resolver
from .source import Source


def update_graph(old_graph: Graph, changed_files: list[str], source: Source) -> Graph:
    """Incrementally update an existing graph by re-extracting only modified files."""
    new_graph = Graph()

    # Copy unchanged modules
    changed_set = set(changed_files)
    for path, mod in old_graph.modules.items():
        if path not in changed_set:
            new_graph.modules[path] = mod
            for c in mod.classes:
                new_graph.classes[c.id] = c
            for f in mod.defs:
                new_graph.functions[f.id] = f

    # Re-extract changed files
    for path in changed_files:
        try:
            data = source.read(path)
            mod_info = extract_file(path, data)
            new_graph.modules[path] = mod_info
            for c in mod_info.classes:
                new_graph.classes[c.id] = c
            for f in mod_info.defs:
                new_graph.functions[f.id] = f
        except Exception:
            # File may have been deleted
            pass

    # Re-resolve whole repo
    resolver = Resolver(new_graph.modules)
    resolved_sites = resolver.resolve_all()

    for site in resolved_sites:
        for target_id, tier, via in site.targets:
            from .model import Edge
            new_graph.add_edge(Edge(
                source=site.owner,
                target=target_id,
                kind="CALLS",
                tier=tier,
                via=via,
                lines=[site.line] if site.line else [],
            ))

    # Recompute reachability
    new_graph.reach_info = compute_reach(new_graph)
    return new_graph
