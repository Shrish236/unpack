"""Graph assembly: pass 1 (extraction) + pass 2 (resolution) + structural edges + reachability."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from .extract import extract_file, module_name_for
from .model import TIER_AMBIGUOUS, TIER_INFERRED, TIER_RANK
from .resolve import Resolver


@dataclass
class Edge:
    src: str
    dst: str
    tier: str
    via: Optional[str] = None
    line: int = 0
    lines: list = field(default_factory=list)
    raw: str = ""
    count: int = 0
    kinds: set = field(default_factory=set)       # call | property | with | ref
    candidates: list = field(default_factory=list)
    sites: list = field(default_factory=list)     # [(guards, kwargs, npos, splat)] per call site


@dataclass
class ImportEdge:
    src: str
    dst: str
    names: list
    level: int
    context: str


class Graph:
    def __init__(self):
        self.mods: dict = {}
        self.funcs: dict = {}
        self.classes: dict = {}
        self.resolver: Optional[Resolver] = None
        self.sites: list = []
        self.calls: dict = {}            # (src,dst) -> Edge
        self.inherits: list = []         # (child, parent)
        self.overrides: list = []        # (method, overridden)
        self.imports: list = []          # ImportEdge
        self.unresolved: dict = {}       # fid -> [(line, raw, reason)]
        self.reach: dict = {}            # fid -> ReachInfo (see reach.py)
        self.reach_pairs: dict = {}
        self.reach_pairs_loose: dict = {}
        self.timing: dict = {}
        self.out_adj: dict = {}
        self.in_adj: dict = {}
        self.label: str = ""

    # ---- convenience
    def func_id_by_qual(self, path_suffix: str, qual: str) -> Optional[str]:
        for f in self.funcs.values():
            if f.qualname == qual and f.path.endswith(path_suffix):
                return f.id
        return None


def build_graph(source, resolver_opts: Optional[dict] = None, reach: bool = True,
                files: Optional[list] = None, mods: Optional[dict] = None) -> Graph:
    t0 = time.time()
    g = Graph()
    g.label = getattr(source, "label", "")
    paths = files if files is not None else source.list_files()
    pset = set(paths)
    if mods is None:
        mods = {}
        for p in paths:
            name, pkg = module_name_for(p, lambda x: x in pset)
            mods[p] = extract_file(p, source.read(p), name, pkg)
    g.mods = mods
    t1 = time.time()
    link(g, resolver_opts or {})
    t2 = time.time()
    if reach:
        from .reach import compute_reach
        compute_reach(g)
    t3 = time.time()
    g.timing = {"extract_s": t1 - t0, "resolve_s": t2 - t1, "reach_s": t3 - t2, "total_s": t3 - t0}
    return g


def link(g: Graph, resolver_opts: dict, only_modules: Optional[set] = None, prior: Optional[Graph] = None):
    """Run pass 2 over the modules (all, or `only_modules` re-resolving into `prior`'s sites)."""
    r = Resolver(g.mods, **resolver_opts)
    g.resolver = r
    g.funcs, g.classes = r.funcs, r.classes
    sites: list = []
    for path, m in g.mods.items():
        if only_modules is not None and path not in only_modules and prior is not None:
            sites.extend(s for s in prior.sites if s.path == path)
        else:
            sites.extend(r.resolve_module(m))
    g.sites = sites
    _build_calls(g)
    _build_structure(g)


def _build_calls(g: Graph):
    calls: dict = {}
    unresolved: dict = {}
    for s in g.sites:
        if s.status == "unresolved" and s.kind == "call":
            unresolved.setdefault(s.owner, []).append((s.line, s.raw, s.reason))
        for t in s.targets:
            key = (s.owner, t.fid)
            e = calls.get(key)
            if e is None:
                e = calls[key] = Edge(s.owner, t.fid, t.tier, t.via, s.line, [], s.raw, 0, set(), [])
            elif TIER_RANK[t.tier] < TIER_RANK[e.tier]:
                e.tier, e.via, e.line, e.raw = t.tier, t.via, s.line, s.raw
            e.count += 1
            e.sites.append((s.guards, s.kwargs, s.npos, s.splat) if s.kind == "call" else ((), (), 0, True))
            if s.line not in e.lines:
                e.lines.append(s.line)
            e.kinds.add(s.kind)
            if t.tier == TIER_AMBIGUOUS:
                e.candidates = s.candidates
    # An instance may have its special methods run implicitly (hashing, comparison, repr, ...)
    # wherever it flows.  Static analysis cannot see every such use, so the constructor gets an
    # AMBIGUOUS edge to each of its own dunders.
    r = g.resolver
    for cid in g.classes:
        hit = r.find_member(r.mro(cid), "__init__")
        if not hit or hit[0] != "fn":
            continue
        init = r.pick_func(hit[2])
        for name, fs in r.members.get(cid, {}).items():
            if name.startswith("__") and name.endswith("__") and name not in (
                    "__init__", "__new__", "__init_subclass__", "__class_getitem__", "__set_name__"):
                d = r.pick_func(fs)
                if d is None or d.is_property or (init.id, d.id) in calls:
                    continue
                calls[(init.id, d.id)] = Edge(init.id, d.id, TIER_AMBIGUOUS, "instance_protocol", init.start,
                                              [init.start], "", 1, {"protocol"}, [], [((), (), 0, True)])
    for cid, c in g.classes.items():
        if r.is_enum(cid) and not c.is_nested:
            fs = r.members.get(cid, {}).get("__new__")
            if fs:
                f = r.pick_func(fs)
                calls[(c.path, f.id)] = Edge(c.path, f.id, TIER_INFERRED, "enum_metaclass", c.start, [c.start],
                                             "", 1, {"protocol"}, [], [((), (), 0, True)])
    for e in calls.values():
        e.lines.sort()
    g.calls = calls
    g.unresolved = unresolved
    out, inn = {}, {}
    for (a, b), e in calls.items():
        out.setdefault(a, []).append(e)
        inn.setdefault(b, []).append(e)
    g.out_adj, g.in_adj = out, inn


def _build_structure(g: Graph):
    r = g.resolver
    g.inherits, g.overrides, g.imports = [], [], []
    for cid in g.classes:
        for b in r.bases(cid):
            g.inherits.append((cid, b))
    for fid, f in g.funcs.items():
        if not f.class_id:
            continue
        seen = set()
        for b in r.bases(f.class_id):
            for c in r.mro(b):
                fs = r.members.get(c, {}).get(f.name)
                if fs:
                    tgt = r.pick_func(fs, want_setter=f.is_setter)
                    if tgt is not None and tgt.id not in seen:
                        seen.add(tgt.id)
                        g.overrides.append((fid, tgt.id))
                    break
    # imports
    agg: dict = {}
    for m in g.mods.values():
        for rec in m.imports:
            targets = []
            if rec.kind == "import":
                for nm, al in rec.names:
                    tm = r.find_module(m, nm)
                    if tm:
                        targets.append((tm, [al and f"{nm} as {al}" or nm]))
            else:
                absm = r.abs_module(m, rec.level, rec.module)
                tm = r.find_module(m, absm, rec.level) if absm else None
                names = [f"{n} as {a}" if a else n for n, a in rec.names] + (["*"] if rec.star else [])
                if tm is not None:
                    targets.append((tm, names))
                for n, a in rec.names:
                    sub = (absm + "." + n) if absm else n
                    sm = r.find_module(m, sub, rec.level)
                    if sm is not None and sm is not tm:
                        targets.append((sm, [n]))
            for tm, names in targets:
                if tm.path == m.path:
                    continue
                key = (m.path, tm.path, rec.context)
                e = agg.get(key)
                if e is None:
                    agg[key] = ImportEdge(m.path, tm.path, list(names), rec.level, rec.context)
                else:
                    for n in names:
                        if n not in e.names:
                            e.names.append(n)
    g.imports = list(agg.values())
