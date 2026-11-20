"""Test reachability: BFS from every test (and its fixtures) over CALLS edges, depth <= 8."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from .model import TIER_AMBIGUOUS, TIER_EXTRACTED, TIER_INFERRED

MAX_DEPTH = 12     # spec says 8; a stress test against real coverage (eval/depth_sweep) saturates at 12


@dataclass
class ReachInfo:
    label: str = "none"             # direct | reached | reached_uncertain | none | test
    count: int = 0
    min_depth: int = 0
    path: list = field(default_factory=list)
    uncertain_count: int = 0
    uncertain_depth: int = 0
    uncertain_path: list = field(default_factory=list)
    unresolved_hint: int = 0        # unresolved test call sites whose method name matches


def _fixture_closure(g, test) -> list:
    """Fixtures a test uses (param names, usefixtures, autouse), transitively, in order."""
    r = g.resolver
    out, seen = [], set()

    def add_for(f):
        names = [p[0] for p in f.params if p[0] not in ("self", "cls")]
        names += list(f.usefixtures)
        for n in names:
            fx = r.visible_fixture(f, n)
            if fx is not None and fx.id not in seen and fx.id != f.id:
                seen.add(fx.id)
                out.append(fx)
                add_for(fx)

    # autouse fixtures visible to the test
    for fx in _autouse_for(g, test):
        if fx.id not in seen:
            seen.add(fx.id)
            out.append(fx)
            add_for(fx)
    add_for(test)
    return out


def _autouse_for(g, test) -> list:
    r = g.resolver
    cached = getattr(g, "_autouse_cache", None)
    if cached is None:
        cached = g._autouse_cache = {}
    res = []
    if test.class_id:
        res += [f for f in r.class_fixtures.get(test.class_id, {}).values() if f.fixture_autouse]
    res += [f for f in r.fixtures.get(test.path, {}).values() if f.fixture_autouse]
    d = test.path.rsplit("/", 1)[0] if "/" in test.path else ""
    while True:
        cp = (d + "/" if d else "") + "conftest.py"
        res += [f for f in r.fixtures.get(cp, {}).values() if f.fixture_autouse]
        if not d:
            break
        d = d.rsplit("/", 1)[0] if "/" in d else ""
    return res


_FALSY = {"None", "False", "0", "0.0", '""', "''", "()", "[]", "{}", 'b""', "b''"}


def _passes(dst, kwargs, npos, splat):
    """Parameters of `dst` supplied by a call site (None = unknown: *args/**kwargs expansion)."""
    if splat or dst is None:
        return None
    names = [p[0] for p in dst.params]
    if dst.is_method and not dst.is_staticmethod and names:
        names = names[1:]                           # bound self / cls
    return frozenset(set(kwargs) | set(names[:npos]))


def build_gated_adjacency(g, tiers) -> tuple:
    """adjacency[a] = [(b, [(needed_params, supplied_params_or_None)])]; and guard-param sets.

    A call is *gated* when it sits inside `if p:` / `if p is not None:` for a parameter `p` of the
    caller that defaults to a falsy value and is never re-assigned.  Such a call can only run when the
    path into the caller actually supplies `p`.  Anything we are not sure about stays ungated."""
    adj: dict = {}
    gp: dict = {}
    for (a, b), e in g.calls.items():
        if e.tier not in tiers:
            continue
        f = g.funcs.get(a)
        dst = g.funcs.get(b)
        sites = []
        for guards, kwargs, npos, splat in (e.sites or [((), (), 0, True)]):
            need = ()
            if f is not None and guards:
                need = tuple(x for x in guards if f.param_defaults.get(x) in _FALSY and x not in f.rebound)
            if need:
                gp.setdefault(a, set()).update(need)
            sites.append((need, _passes(dst, kwargs, npos, splat)))
        adj.setdefault(a, []).append((b, sites))
    return adj, {k: frozenset(v) for k, v in gp.items()}


def _bfs(starts: list, adj: dict, gp: dict) -> dict:
    """starts: [(node, depth, path)]; returns node -> (depth, parent, path) of its first visit.

    The search runs over (node, supplied-guard-params) states so that a gated call is only followed
    when the incoming call supplied the guarding argument."""
    seen: dict = {}
    states: set = set()
    dq = deque()
    for n, d, path in starts:
        if (n, None) not in states:
            states.add((n, None))
            if n not in seen:
                seen[n] = (d, path[-2] if len(path) > 1 else None, tuple(path))
            dq.append((n, None, d, tuple(path)))
    while dq:
        n, S, d, path = dq.popleft()
        if d >= MAX_DEPTH:
            continue
        for b, sites in adj.get(n, ()):
            allowed = [(need, sup) for need, sup in sites if S is None or set(need) <= S]
            if not allowed:
                continue
            if any(sup is None for _n, sup in allowed):
                Sb = None
            else:
                Sb = frozenset().union(*[sup for _n, sup in allowed]) & gp.get(b, frozenset())
            key = (b, Sb)
            if key in states:
                continue
            states.add(key)
            npath = path + (b,)
            if b not in seen:
                seen[b] = (d + 1, n, npath)
            dq.append((b, Sb, d + 1, npath))
    return seen


def path_of(seen: dict, node: str) -> list:
    return list(seen[node][2])


def implicitly_invoked(g, f) -> bool:
    """A function that code outside the static graph can call, so `none` would overstate what we know.

    * a dunder method: the interpreter calls it (repr, comparison, hashing, iteration, ...);
    * a closure (defined inside a function): created at run time, and whoever receives it calls it;
    * a method of a class with a base outside the repository: that base can call it.
    """
    if f.name.startswith("__") and f.name.endswith("__"):
        return True
    if f.is_nested and f.parent_func is not None:
        return True
    if f.class_id is not None:
        cls = g.classes[f.class_id]
        if any(not (g.resolver.class_expr(b, g.mods[cls.path]) or ("",))[0] == "cls"
               for b in cls.bases_raw):
            return True
    return False


def compute_reach(g, include_refs: bool = True, implicit_uncertain: bool = True):
    ok = (TIER_EXTRACTED, TIER_INFERRED)
    certain, gp_c = build_gated_adjacency(g, ok)
    loose, gp_l = build_gated_adjacency(g, ok + (TIER_AMBIGUOUS,))
    if not include_refs:
        for adjm in (certain, loose):
            for a in list(adjm):
                adjm[a] = [(b, st) for b, st in adjm[a] if g.calls[(a, b)].kinds != {"ref"}]
    tests = [f for f in g.funcs.values() if f.is_test]
    info = {fid: ReachInfo() for fid in g.funcs}
    pairs_c: dict = {}
    pairs_l: dict = {}
    imp_adj: dict = {}
    for ie in g.imports:
        if ie.context == "runtime":
            imp_adj.setdefault(ie.src, []).append(ie.dst)
    by_name = g.resolver.mod_by_name
    closure_cache: dict = {}

    def import_closure(path: str) -> list:
        """Modules executed (module-level code) when pytest loads the test module at `path`."""
        if path in closure_cache:
            return closure_cache[path]
        roots = [path]
        d = path.rsplit("/", 1)[0] if "/" in path else ""
        while True:                                  # conftest.py files of the directory chain
            cp = (d + "/" if d else "") + "conftest.py"
            if cp in g.mods and cp != path:
                roots.append(cp)
            if not d:
                break
            d = d.rsplit("/", 1)[0] if "/" in d else ""
        seen, dq = [], deque(roots)
        have = set()
        while dq:
            m = dq.popleft()
            if m in have or m not in g.mods:
                continue
            have.add(m)
            seen.append(m)
            dq.extend(imp_adj.get(m, ()))
            parts = g.mods[m].name.split(".")        # importing a.b.c also imports packages a and a.b
            for i in range(1, len(parts)):
                pm = by_name.get(".".join(parts[:i]))
                if pm is not None:
                    dq.append(pm.path)
        closure_cache[path] = sorted(seen)
        return closure_cache[path]

    for t in sorted(tests, key=lambda f: f.id):
        fixtures = _fixture_closure(g, t)
        starts = [(t.id, 0, (t.id,))] + [(fx.id, 1, (t.id, fx.id)) for fx in fixtures]
        starts += [(m, 1, (t.id, m)) for m in import_closure(t.path)]
        sc = _bfs(starts, certain, gp_c)
        pairs_c[t.id] = sc
        sl = _bfs(starts, loose, gp_l)
        pairs_l[t.id] = sl
        for node, (d, par, _pth) in sc.items():
            if node == t.id or d == 0:
                continue
            ri = info.get(node)
            if ri is None:
                continue
            ri.count += 1
            if ri.min_depth == 0 or d < ri.min_depth:
                ri.min_depth = d
                ri.path = path_of(sc, node)
        for node, (d, par, _pth) in sl.items():
            if node in sc or d == 0:
                continue
            ri = info.get(node)
            if ri is None:
                continue
            ri.uncertain_count += 1
            if ri.uncertain_depth == 0 or d < ri.uncertain_depth:
                ri.uncertain_depth = d
                ri.uncertain_path = path_of(sl, node)
    for fid, ri in info.items():
        f = g.funcs[fid]
        if f.is_test:
            ri.label = "test"
        elif ri.count:
            ri.label = "direct" if ri.min_depth == 1 else "reached"
        elif ri.uncertain_count:
            ri.label = "reached_uncertain"
        elif implicit_uncertain and implicitly_invoked(g, f):
            # no static path, but runtime machinery calls this kind of function: not a proof of
            # "untested", so it is uncertain rather than none
            ri.label = "reached_uncertain"
        else:
            ri.label = "none"
    # hint: unresolved/ambiguous test call sites whose method name equals this function's name
    names: dict = {}
    for s in g.sites:
        if s.kind == "call" and s.status in ("unresolved", "ambiguous") and g.mods[s.path].is_test:
            last = s.raw.split("(")[0].split(".")[-1].strip()
            names[last] = names.get(last, 0) + 1
    for fid, ri in info.items():
        if ri.label == "none":
            ri.unresolved_hint = names.get(g.funcs[fid].name, 0)
    g.reach = info
    g.reach_pairs = pairs_c
    g.reach_pairs_loose = pairs_l
