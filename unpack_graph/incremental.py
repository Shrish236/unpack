"""Incremental update (spec section 7).

  1. re-extract only the changed files (pass 1) and drop deleted ones;
  2. rebuild the cheap global indices;
  3. re-resolve the outgoing calls of every *affected* file, reuse every other file's sites:
       - the changed files themselves,
       - files that import them, two hops out (their targets may have moved),
       - files that define ancestors of classes in changed files (override dispatch fans out to
         the changed subclasses) and their direct importers,
       - files that hold name-dependent sites (unique-name / ambiguous / unresolved) whose method name
         was added or removed;
  4. rebuild edges/structure and recompute test reachability.

`verify()` compares the result with a full rebuild; tests and the eval run it on real commits.
"""
from __future__ import annotations

import time
from typing import Optional

from .extract import extract_file, module_name_for
from .graph import Graph, _build_calls, _build_structure
from .resolve import Resolver


def _importers(imports: list, paths: set, hops: int) -> set:
    rev: dict = {}
    for e in imports:
        rev.setdefault(e.dst, set()).add(e.src)
    out, frontier = set(), set(paths)
    for _ in range(hops):
        nxt = set()
        for p in frontier:
            nxt |= rev.get(p, set())
        nxt -= out
        out |= nxt
        frontier = nxt
    return out


def update_graph(old: Graph, source, changed: set, deleted: set, resolver_opts: Optional[dict] = None,
                 hops: int = 2) -> tuple:
    """Return (new_graph, stats).  `changed` = added or modified paths, `deleted` = removed paths."""
    t0 = time.time()
    opts = resolver_opts or {}
    paths = [p for p in source.list_files()]
    pset = set(paths)
    mods = {p: m for p, m in old.mods.items() if p in pset and p not in changed}
    for p in sorted(changed & pset):
        name, pkg = module_name_for(p, lambda x: x in pset)
        mods[p] = extract_file(p, source.read(p), name, pkg)
    # module names depend on __init__.py presence; refresh them for every file (no re-parse needed)
    for p, m in mods.items():
        name, pkg = module_name_for(p, lambda x: x in pset)
        m.name, m.package = name, pkg
    mods = {p: mods[p] for p in paths if p in mods}
    t1 = time.time()

    new = Graph()
    new.label = getattr(source, "label", "")
    new.mods = mods
    r = Resolver(mods, **opts)
    new.resolver = r
    new.funcs, new.classes = r.funcs, r.classes

    seeds = (changed | deleted)
    # imports of the new world (cheap) so we can walk importers in both old and new graphs
    new.sites = []
    _build_structure(new)
    imports = list(old.imports) + list(new.imports)
    affected = set(seeds) | _importers(imports, seeds, hops)

    # ancestors of classes defined in changed files (old and new) -> dispatch fan-out lives there
    anc_files = set()
    for graph, files in ((old, changed | deleted), (new, changed)):
        gr = graph.resolver
        for c in graph.classes.values():
            if c.path in files:
                for a in gr.mro(c.id)[1:]:
                    anc_files.add(graph.classes[a].path)
    affected |= anc_files | _importers(imports, anc_files, 1)

    # method names that appeared/disappeared -> sites that fell back to name matching may change
    def names_of(graph, files):
        return {f.name for f in graph.funcs.values() if f.is_method and f.path in files}
    touched = names_of(old, changed | deleted) ^ names_of(new, changed)
    # (names present on both sides can still change candidate counts; include any name whose
    #  count of defining methods differs)
    def count_by_name(graph):
        c: dict = {}
        for f in graph.funcs.values():
            if f.is_method:
                c[f.name] = c.get(f.name, 0) + 1
        return c
    co, cn = count_by_name(old), count_by_name(new)
    touched |= {n for n in set(co) | set(cn) if co.get(n, 0) != cn.get(n, 0)}
    if touched:
        for s in old.sites:
            if s.kind == "call" and s.path not in affected and (
                    s.status in ("ambiguous", "unresolved") or any(t.via == "unique_name" for t in s.targets)):
                if s.raw.split("(")[0].split(".")[-1].strip() in touched:
                    affected.add(s.path)

    # getattr-dispatched sites depend on the method names of their receiver's class
    if touched:
        for s in old.sites:
            if s.kind != "dynamic" or s.path in affected:
                continue
            kind, _, text = (s.reason or "").partition(":")
            if any((n == text) if kind == "literal" else n.startswith(text) for n in touched):
                affected.add(s.path)

    affected &= set(mods)
    sites: list = []
    reused = 0
    old_by_path: dict = {}
    for s in old.sites:
        old_by_path.setdefault(s.path, []).append(s)
    for p, m in mods.items():
        if p in affected:
            sites.extend(r.resolve_module(m))
        else:
            sites.extend(old_by_path.get(p, []))
            reused += 1
    new.sites = sites
    _build_calls(new)
    _build_structure(new)
    t2 = time.time()
    from .reach import compute_reach
    compute_reach(new)
    t3 = time.time()
    stats = {"files": len(mods), "changed": len(changed), "deleted": len(deleted),
             "affected": len(affected), "affected_files": sorted(affected), "reused": reused,
             "reparse_s": t1 - t0, "relink_s": t2 - t1, "reach_s": t3 - t2, "total_s": t3 - t0}
    new.timing = {"total_s": t3 - t0}
    return new, stats


def graph_fingerprint(g: Graph) -> dict:
    """Canonical content of a graph for equality checks (full rebuild vs incremental)."""
    calls = {(a, b): (e.tier, e.via, tuple(e.lines), e.count, tuple(sorted(e.kinds)), tuple(e.candidates))
             for (a, b), e in g.calls.items()}
    reach = {fid: (ri.label, ri.count, ri.min_depth, tuple(ri.path), ri.uncertain_count, ri.uncertain_depth)
             for fid, ri in g.reach.items()}
    return {"funcs": {f.id: (f.start, f.end, f.logic_hash, f.signature_hash) for f in g.funcs.values()},
            "classes": {c.id: (c.start, c.end, tuple(c.bases_raw)) for c in g.classes.values()},
            "calls": calls, "inherits": sorted(g.inherits), "overrides": sorted(g.overrides),
            "imports": sorted((e.src, e.dst, e.context, tuple(e.names)) for e in g.imports),
            "unresolved": {k: tuple(v) for k, v in g.unresolved.items()}, "reach": reach}


def diff_fingerprints(a: dict, b: dict, limit: int = 5) -> dict:
    out = {}
    for k in a:
        if a[k] == b[k]:
            continue
        if isinstance(a[k], dict):
            ka, kb = set(a[k]), set(b[k])
            diffs = [x for x in ka & kb if a[k][x] != b[k][x]]
            out[k] = {"only_a": len(ka - kb), "only_b": len(kb - ka), "different": len(diffs),
                      "examples": [str(x) for x in (sorted(ka - kb)[:limit] + sorted(kb - ka)[:limit] + sorted(diffs)[:limit])]}
        else:
            out[k] = {"a": len(a[k]), "b": len(b[k])}
    return out
