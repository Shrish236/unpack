"""Neo4j loader and the region Cypher query.

Schema (see the task spec): Module / Class / Function nodes (+ :Test label on test functions,
+ :Ghost on deleted functions) and CONTAINS / HAS_METHOD / INHERITS / OVERRIDES / IMPORTS /
CALLS / REACHES relationships.  All writes are batched with UNWIND in chunks of 500.
"""
from __future__ import annotations

import json
import os
import time

from neo4j import GraphDatabase

from .graph import Graph
from .region import DEFAULT_CAP, DEFAULT_TESTS_PER_NODE, class_props, func_props, to_contract
from .reach import path_of

CHUNK = 500
URI = os.environ.get("UNPACK_NEO4J_URI", "bolt://localhost:7687")
USER = os.environ.get("UNPACK_NEO4J_USER", "neo4j")
PASSWORD = os.environ.get("UNPACK_NEO4J_PASSWORD", "unpackpass")


def connect(uri: str = URI, user: str = USER, password: str = PASSWORD, wait_s: float = 60.0):
    driver = GraphDatabase.driver(uri, auth=(user, password), notifications_min_severity="OFF")
    t0 = time.time()
    while True:
        try:
            driver.verify_connectivity()
            return driver
        except Exception:
            if time.time() - t0 > wait_s:
                raise
            time.sleep(1.0)


def _chunks(rows: list, n: int = CHUNK):
    for i in range(0, len(rows), n):
        yield rows[i:i + n]


def _run_batched(session, query: str, rows: list):
    for ch in _chunks(rows):
        session.run(query, rows=ch).consume()


SCHEMA_STMTS = [
    "CREATE INDEX module_id IF NOT EXISTS FOR (n:Module) ON (n.id)",
    "CREATE INDEX module_path IF NOT EXISTS FOR (n:Module) ON (n.path)",
    "CREATE INDEX module_name IF NOT EXISTS FOR (n:Module) ON (n.name)",
    "CREATE INDEX class_id IF NOT EXISTS FOR (n:Class) ON (n.id)",
    "CREATE INDEX class_path IF NOT EXISTS FOR (n:Class) ON (n.path)",
    "CREATE INDEX class_name IF NOT EXISTS FOR (n:Class) ON (n.name)",
    "CREATE INDEX function_id IF NOT EXISTS FOR (n:Function) ON (n.id)",
    "CREATE INDEX function_path IF NOT EXISTS FOR (n:Function) ON (n.path)",
    "CREATE INDEX function_name IF NOT EXISTS FOR (n:Function) ON (n.name)",
    "CREATE INDEX function_qualname IF NOT EXISTS FOR (n:Function) ON (n.qualname)",
    "CREATE INDEX function_path_name IF NOT EXISTS FOR (n:Function) ON (n.path, n.name)",
    "CREATE INDEX function_label IF NOT EXISTS FOR (n:Function) ON (n.test_label)",
    "CREATE INDEX class_qualname IF NOT EXISTS FOR (n:Class) ON (n.qualname)",
    "CREATE INDEX calls_tier IF NOT EXISTS FOR ()-[r:CALLS]-() ON (r.tier)",
    "CREATE INDEX reaches_depth IF NOT EXISTS FOR ()-[r:REACHES]-() ON (r.depth)",
]


def ensure_schema(driver):
    with driver.session() as s:
        for stmt in SCHEMA_STMTS:
            s.run(stmt).consume()
        s.run("CALL db.awaitIndexes(60)").consume()


def clear(driver):
    with driver.session() as s:
        while True:
            n = s.run("MATCH (n) WITH n LIMIT 20000 DETACH DELETE n RETURN count(*) AS c").single()["c"]
            if n == 0:
                break


# ------------------------------------------------------------------ row builders
def module_rows(g: Graph) -> list:
    return [{"id": m.id, "path": m.path, "name": m.name, "is_test": m.is_test, "package": m.package,
             "partial": m.partial, "is_init": m.is_init, "nlines": m.nlines}
            for m in g.mods.values()]


def class_rows(g: Graph) -> list:
    return [class_props(c) for c in g.classes.values()]


def function_rows(g: Graph) -> list:
    rows = []
    for fid, f in g.funcs.items():
        p = func_props(f)
        p["in_test_module"] = g.mods[f.path].is_test
        p["ghost"] = False
        ri = g.reach.get(fid)
        if ri is not None:
            p.update({"test_label": ri.label, "test_count": ri.count, "test_min_depth": ri.min_depth,
                      "test_path": list(ri.path), "test_unc_count": ri.uncertain_count,
                      "test_unc_depth": ri.uncertain_depth, "test_unc_path": list(ri.uncertain_path),
                      "unresolved_hint": ri.unresolved_hint})
        un = g.unresolved.get(fid)
        p["unresolved_calls"] = [f"{line}|{why}|{raw}" for line, raw, why in un] if un else []
        rows.append(p)
    return rows


def _edge_props(e) -> dict:
    return {"tier": e.tier, "via": e.via, "line": e.line, "lines": list(e.lines), "raw": e.raw,
            "count": e.count, "candidates": list(e.candidates)}


def calls_rows(g: Graph):
    fn_fn, mod_fn = [], []
    for (a, b), e in g.calls.items():
        row = {"src": a, "dst": b, "p": _edge_props(e)}
        (fn_fn if "::" in a else mod_fn).append(row)
    return fn_fn, mod_fn


def reach_rows(g: Graph) -> list:
    rows = []
    for tid in sorted(g.reach_pairs):
        sc = g.reach_pairs[tid]
        sl = g.reach_pairs_loose[tid]
        for node, (d, _par, _p) in sc.items():
            if d > 0 and node != tid and node in g.funcs:
                rows.append({"src": tid, "dst": node, "depth": d, "path": path_of(sc, node), "uncertain": False})
        for node, (d, _par, _p) in sl.items():
            if node not in sc and d > 0 and node != tid and node in g.funcs:
                rows.append({"src": tid, "dst": node, "depth": d, "path": path_of(sl, node), "uncertain": True})
    return rows


def structure_rows(g: Graph) -> dict:
    contains = {"Module-Class": [], "Module-Function": [], "Function-Function": [], "Function-Class": [],
                "Class-Class": []}
    has_method = []
    for c in g.classes.values():
        if c.parent_class:
            contains["Class-Class"].append({"src": c.parent_class, "dst": c.id})
        elif c.parent_func:
            contains["Function-Class"].append({"src": c.parent_func, "dst": c.id})
        else:
            contains["Module-Class"].append({"src": c.path, "dst": c.id})
    for f in g.funcs.values():
        if f.class_id:
            has_method.append({"src": f.class_id, "dst": f.id})
        elif f.parent_func:
            contains["Function-Function"].append({"src": f.parent_func, "dst": f.id})
        else:
            contains["Module-Function"].append({"src": f.path, "dst": f.id})
    return {
        "contains": contains, "has_method": has_method,
        "inherits": [{"src": a, "dst": b} for a, b in g.inherits],
        "overrides": [{"src": a, "dst": b} for a, b in g.overrides],
        "imports": [{"src": e.src, "dst": e.dst, "names": e.names, "level": e.level, "context": e.context}
                    for e in g.imports],
    }


# ------------------------------------------------------------------ loading
def load_graph(g: Graph, driver, wipe: bool = True, with_reaches: bool = True) -> dict:
    """Full load. Returns timings and row counts."""
    t0 = time.time()
    if wipe:
        clear(driver)
    ensure_schema(driver)
    counts = {}
    with driver.session() as s:
        mods = module_rows(g)
        _run_batched(s, "UNWIND $rows AS r CREATE (n:Module) SET n = r", mods)
        classes = class_rows(g)
        _run_batched(s, "UNWIND $rows AS r CREATE (n:Class) SET n = r", classes)
        funcs = function_rows(g)
        _run_batched(s, """UNWIND $rows AS r CREATE (n:Function) SET n = r
                           FOREACH (_ IN CASE WHEN r.is_test THEN [1] ELSE [] END | SET n:Test)""", funcs)
        counts.update(modules=len(mods), classes=len(classes), functions=len(funcs))
        st = structure_rows(g)
        for k, rows in st["contains"].items():
            a, b = k.split("-")
            _run_batched(s, f"UNWIND $rows AS r MATCH (a:{a} {{id: r.src}}) MATCH (b:{b} {{id: r.dst}}) CREATE (a)-[:CONTAINS]->(b)", rows)
        _run_batched(s, "UNWIND $rows AS r MATCH (a:Class {id: r.src}) MATCH (b:Function {id: r.dst}) CREATE (a)-[:HAS_METHOD]->(b)", st["has_method"])
        _run_batched(s, "UNWIND $rows AS r MATCH (a:Class {id: r.src}) MATCH (b:Class {id: r.dst}) CREATE (a)-[:INHERITS]->(b)", st["inherits"])
        _run_batched(s, "UNWIND $rows AS r MATCH (a:Function {id: r.src}) MATCH (b:Function {id: r.dst}) CREATE (a)-[:OVERRIDES]->(b)", st["overrides"])
        _run_batched(s, "UNWIND $rows AS r MATCH (a:Module {id: r.src}) MATCH (b:Module {id: r.dst}) CREATE (a)-[:IMPORTS {names: r.names, level: r.level, context: r.context}]->(b)", st["imports"])
        ff, mf = calls_rows(g)
        _run_batched(s, "UNWIND $rows AS r MATCH (a:Function {id: r.src}) MATCH (b:Function {id: r.dst}) CREATE (a)-[c:CALLS]->(b) SET c = r.p", ff)
        _run_batched(s, "UNWIND $rows AS r MATCH (a:Module {id: r.src}) MATCH (b:Function {id: r.dst}) CREATE (a)-[c:CALLS]->(b) SET c = r.p", mf)
        counts.update(calls=len(ff) + len(mf), imports=len(st["imports"]))
        t_struct = time.time()
        if with_reaches:
            rr = reach_rows(g)
            _run_batched(s, "UNWIND $rows AS r MATCH (a:Function {id: r.src}) MATCH (b:Function {id: r.dst}) CREATE (a)-[x:REACHES]->(b) SET x.depth = r.depth, x.path = r.path, x.uncertain = r.uncertain", rr)
            counts["reaches"] = len(rr)
    counts["load_s"] = time.time() - t0
    counts["reaches_s"] = time.time() - t_struct if with_reaches else 0.0
    return counts


def snapshot_signature(g: Graph) -> dict:
    """Comparable summary used to verify DB contents == in-memory graph."""
    ff, mf = calls_rows(g)
    return {"modules": len(g.mods), "classes": len(g.classes), "functions": len(g.funcs),
            "calls": len(ff) + len(mf), "inherits": len(g.inherits), "overrides": len(g.overrides),
            "imports": len(g.imports)}


def db_counts(driver) -> dict:
    with driver.session() as s:
        r = s.run("""
            CALL { MATCH (n:Module) RETURN count(n) AS modules }
            CALL { MATCH (n:Class) RETURN count(n) AS classes }
            CALL { MATCH (n:Function) WHERE NOT n:Ghost RETURN count(n) AS functions }
            CALL { MATCH ()-[r:CALLS]->() WHERE r.via <> 'removed' OR r.via IS NULL RETURN count(r) AS calls }
            CALL { MATCH ()-[r:INHERITS]->() RETURN count(r) AS inherits }
            CALL { MATCH ()-[r:OVERRIDES]->() RETURN count(r) AS overrides }
            CALL { MATCH ()-[r:IMPORTS]->() RETURN count(r) AS imports }
            CALL { MATCH ()-[r:REACHES]->() RETURN count(r) AS reaches }
            RETURN modules, classes, functions, calls, inherits, overrides, imports, reaches""").single()
        return dict(r)


# ------------------------------------------------------------------ change annotation (ghosts, flags)
def annotate_changes(driver, cs) -> dict:
    """Mark changed functions (props) and add ghost nodes for deleted ones. Idempotent."""
    gb = cs.base_graph
    with driver.session() as s:
        s.run("MATCH (n:Ghost) DETACH DELETE n").consume()
        s.run("""MATCH (f:Function) WHERE f.change_kind IS NOT NULL
                 REMOVE f.change_kind, f.change_flags, f.change_head_lines, f.change_base_lines,
                        f.change_old_id, f.change_still_called_by""").consume()
        live, ghosts, ghost_edges = [], [], []
        for c in cs.functions:
            row = {"change_kind": c.kind, "change_flags": list(c.flags),
                   "change_head_lines": json.dumps(c.head_lines), "change_base_lines": json.dumps(c.base_lines),
                   "change_old_id": c.old_id, "change_still_called_by": list(c.still_called_by)}
            if c.kind == "deleted":
                f = gb.funcs[c.id]
                p = func_props(f)
                p.update(row)
                p.update({"in_test_module": gb.mods[f.path].is_test, "ghost": True, "unresolved_calls": []})
                ghosts.append(p)
                for caller in c.still_called_by:
                    be = gb.calls.get((caller, c.id))
                    props = {"tier": be.tier if be else "EXTRACTED", "via": "removed",
                             "line": be.line if be else 0, "lines": list(be.lines) if be else [],
                             "raw": be.raw if be else "", "count": be.count if be else 0, "candidates": []}
                    ghost_edges.append({"src": caller, "dst": c.id, "p": props})
            else:
                live.append({"id": c.id, "p": row})
        _run_batched(s, "UNWIND $rows AS r MATCH (f:Function {id: r.id}) WHERE NOT f:Ghost SET f += r.p", live)
        _run_batched(s, "UNWIND $rows AS r CREATE (n:Function:Ghost) SET n = r", ghosts)
        _run_batched(s, "UNWIND $rows AS r MATCH (a:Function {id: r.src}) WHERE NOT a:Ghost MATCH (b:Ghost {id: r.dst}) CREATE (a)-[c:CALLS]->(b) SET c = r.p", ghost_edges)
    return {"annotated": len(live), "ghosts": len(ghosts)}


# ------------------------------------------------------------------ region query (single Cypher statement)
REGION_CYPHER = """
UNWIND range(0, size($ids) - 1) AS ord
WITH ord, $ids[ord] AS fid
MATCH (f:Function {id: fid})
CALL {
  WITH f
  MATCH (c:Function)-[r:CALLS]->(f)
  WHERE c.id <> f.id AND NOT c.in_test_module
  WITH f, c, r
  ORDER BY CASE r.tier WHEN 'EXTRACTED' THEN 0 WHEN 'INFERRED' THEN 1 WHEN 'AMBIGUOUS' THEN 2 ELSE 3 END,
           -coalesce(c.test_count, 0), c.id
  LIMIT $cap
  RETURN collect({n: properties(c), e: properties(r), src: c.id, dst: f.id}) AS callers
}
CALL {
  WITH f
  MATCH (f)-[r:CALLS]->(c:Function)
  WHERE c.id <> f.id AND NOT c.in_test_module
  WITH f, c, r
  ORDER BY CASE r.tier WHEN 'EXTRACTED' THEN 0 WHEN 'INFERRED' THEN 1 WHEN 'AMBIGUOUS' THEN 2 ELSE 3 END,
           -coalesce(c.test_count, 0), c.id
  LIMIT $cap
  RETURN collect({n: properties(c), e: properties(r), src: f.id, dst: c.id}) AS callees
}
CALL {
  WITH f
  OPTIONAL MATCH (k:Class)-[:HAS_METHOD]->(f)
  OPTIONAL MATCH (k)-[:INHERITS]->(b:Class)
  RETURN properties(k) AS klass, [x IN collect(DISTINCT properties(b)) WHERE x IS NOT NULL] AS bases
}
CALL {
  WITH f
  OPTIONAL MATCH (f)-[:OVERRIDES]->(o:Function)
  RETURN [x IN collect(DISTINCT properties(o)) WHERE x IS NOT NULL] AS overridden
}
CALL {
  WITH f
  OPTIONAL MATCH (m:Function)-[:OVERRIDES]->(f)
  RETURN [x IN collect(DISTINCT properties(m)) WHERE x IS NOT NULL] AS overriders
}
CALL {
  WITH f
  OPTIONAL MATCH (t:Test)-[x:REACHES]->(f)
  WHERE x.uncertain = (f.test_label = 'reached_uncertain') AND t.id <> f.id
  WITH t, x
  ORDER BY CASE WHEN t.path IN $changed_paths THEN 0 ELSE 1 END, x.depth, t.id
  LIMIT $tests_per_node
  RETURN [y IN collect({n: properties(t), depth: x.depth, path: x.path}) WHERE y.n IS NOT NULL] AS tests
}
RETURN ord, properties(f) AS f, callers, callees, klass, bases, overridden, overriders, tests
ORDER BY ord
"""

_FUNC_KEYS = ["id", "name", "qualname", "path", "start", "end", "is_async", "is_method", "is_test", "is_fixture",
              "is_abstract", "is_property", "decorators", "signature", "doc", "body_hash", "logic_hash",
              "signature_hash"]
_CLASS_KEYS = ["id", "name", "qualname", "path", "start", "end", "bases_raw", "bases"]


def _fprops(p: dict) -> dict:
    return {k: p.get(k) for k in _FUNC_KEYS}


def _tests_from_props(p: dict, tests: list) -> dict:
    label = p.get("test_label")
    if label == "reached_uncertain":
        count, depth, path = p.get("test_unc_count", 0), p.get("test_unc_depth", 0), p.get("test_unc_path", [])
    else:
        count, depth, path = p.get("test_count", 0), p.get("test_min_depth", 0), p.get("test_path", [])
    # a test's own label says nothing about which tests reach it: list none, as the in-memory
    # region does (a test can be reached by another test through import-time code)
    listed = [] if label in ("test", None) else tests
    return {"label": label, "count": count, "min_depth": depth, "path": list(path or []),
            "tests": [{"id": t["n"]["id"], "depth": t["depth"]} for t in listed],
            "unresolved_hint": p.get("unresolved_hint", 0)}


def region_query(driver, cs, cap: int = DEFAULT_CAP, tests_per_node: int = DEFAULT_TESTS_PER_NODE) -> dict:
    """Run REGION_CYPHER for the changed ids and shape the rows into a GraphView.

    All selection (one-hop expansion, ranking by tier then test count, capping, test selection)
    happens in the single Cypher statement; Python only assembles the returned rows.
    """
    from .region import VERSION
    order = [c.id for c in cs.functions]
    changes = {c.id: c for c in cs.functions}
    with driver.session() as s:
        rows = s.run(REGION_CYPHER, ids=order, cap=cap, tests_per_node=tests_per_node,
                     changed_paths=sorted({np_ for _st, _op, np_ in cs.files})).data()
    byid = {r["f"]["id"]: r for r in rows}
    nodes: dict = {}
    edges: dict = {}

    def change_of(fid):
        c = changes.get(fid)
        if c is None:
            return None
        return {"kind": c.kind, "flags": list(c.flags), "head_lines": c.head_lines, "base_lines": c.base_lines,
                "old_id": c.old_id, "still_called_by": list(c.still_called_by)}

    def add_func(p, role, tests=None, change=None):
        fid = p["id"]
        if fid in nodes:
            if role == "changed":
                nodes[fid]["role"] = role
            return
        ghost = bool(p.get("ghost"))
        nodes[fid] = {"id": fid, "type": "Function", "role": role, "ghost": ghost, "props": _fprops(p),
                      "change": change, "tests": None if ghost else _tests_from_props(p, tests or [])}

    def add_edge(d):
        edges[(d["source"], d["target"], d["kind"])] = d

    def calls_edge(src, dst, e):
        return {"source": src, "target": dst, "kind": "CALLS", "tier": e["tier"], "via": e.get("via"),
                "line": e.get("line", 0), "lines": list(e.get("lines") or []), "count": e.get("count", 0),
                "raw": e.get("raw", ""), "candidates": list(e.get("candidates") or [])}

    def plain(src, dst, typ):
        return {"source": src, "target": dst, "kind": typ, "tier": "EXTRACTED", "via": None, "line": 0,
                "lines": [], "count": 0, "raw": "", "candidates": []}

    # pass 1: all changed / ghost nodes first (matches the in-memory builder's insertion order)
    for fid in order:
        r = byid.get(fid)
        if r is None:
            continue
        p = r["f"]
        if p.get("ghost"):
            add_func(p, "ghost", change=change_of(fid))
        else:
            add_func(p, "changed", None, change_of(fid))
            nodes[fid]["tests"] = _tests_from_props(p, r["tests"])
    for fid in order:
        r = byid.get(fid)
        if r is None:
            continue
        p = r["f"]
        if p.get("ghost"):
            for c in r["callers"]:
                add_func(c["n"], "caller")
                add_edge(calls_edge(c["src"], c["dst"], c["e"]))
            continue
        for c in r["callers"]:
            add_func(c["n"], "caller")
            add_edge(calls_edge(c["src"], c["dst"], c["e"]))
        for c in r["callees"]:
            add_func(c["n"], "callee")
            add_edge(calls_edge(c["src"], c["dst"], c["e"]))
        if r["klass"]:
            k = r["klass"]
            if k["id"] not in nodes:
                nodes[k["id"]] = {"id": k["id"], "type": "Class", "role": "parent_class", "ghost": False,
                                  "props": {x: k.get(x) for x in _CLASS_KEYS}, "change": None, "tests": None}
            add_edge(plain(k["id"], fid, "HAS_METHOD"))
            for b in r["bases"]:
                if b["id"] not in nodes:
                    nodes[b["id"]] = {"id": b["id"], "type": "Class", "role": "base_class", "ghost": False,
                                      "props": {x: b.get(x) for x in _CLASS_KEYS}, "change": None, "tests": None}
                add_edge(plain(k["id"], b["id"], "INHERITS"))
        for o in r["overridden"]:
            add_func(o, "overridden")
            add_edge(plain(fid, o["id"], "OVERRIDES"))
        for m in r["overriders"]:
            add_func(m, "overrider")
            add_edge(plain(m["id"], fid, "OVERRIDES"))
        uncertain = p.get("test_label") == "reached_uncertain"
        for t in ([] if p.get("test_label") in ("test", None) else r["tests"]):   # tests list no tests
            add_func(t["n"], "test")
            d = plain(t["n"]["id"], fid, "REACHES")
            d.update({"tier": "AMBIGUOUS" if uncertain else "INFERRED", "depth": t["depth"], "path": list(t["path"])})
            add_edge(d)
    # neighbour / test nodes need their own tests info: fetch from DB properties we already have
    node_list = sorted(nodes.values(), key=lambda n: (n["role"] != "changed", n["role"], n["id"]))
    edge_list = sorted(edges.values(), key=lambda e: (e["kind"], e["source"], e["target"]))
    to_contract(node_list, edge_list)
    from .region import build_meta
    meta = build_meta(cs, [fid for fid in order if fid in byid and not byid[fid]["f"].get("ghost")], cap,
                      tests_per_node)
    return {"version": VERSION, "meta": meta, "nodes": node_list, "edges": edge_list}
# ------------------------------------------------------------------ incremental delta
def graph_rows(g: Graph, with_reaches: bool = True) -> dict:
    """Canonical keyed rows of a graph: {'nodes': {label: {id: props}}, 'rels': {spec: {key: props}}}."""
    nodes = {"Module": {r["id"]: r for r in module_rows(g)},
             "Class": {r["id"]: r for r in class_rows(g)},
             "Function": {r["id"]: r for r in function_rows(g)}}
    rels: dict = {}
    st = structure_rows(g)
    for k, rows in st["contains"].items():
        a, b = k.split("-")
        rels[("CONTAINS", a, b)] = {(r["src"], r["dst"]): {} for r in rows}
    rels[("HAS_METHOD", "Class", "Function")] = {(r["src"], r["dst"]): {} for r in st["has_method"]}
    rels[("INHERITS", "Class", "Class")] = {(r["src"], r["dst"]): {} for r in st["inherits"]}
    rels[("OVERRIDES", "Function", "Function")] = {(r["src"], r["dst"]): {} for r in st["overrides"]}
    rels[("IMPORTS", "Module", "Module")] = {
        (r["src"], r["dst"], r["context"]): {"names": r["names"], "level": r["level"], "context": r["context"]}
        for r in st["imports"]}
    ff, mf = calls_rows(g)
    rels[("CALLS", "Function", "Function")] = {(r["src"], r["dst"]): r["p"] for r in ff}
    rels[("CALLS", "Module", "Function")] = {(r["src"], r["dst"]): r["p"] for r in mf}
    if with_reaches:
        rels[("REACHES", "Function", "Function")] = {
            (r["src"], r["dst"]): {"depth": r["depth"], "path": r["path"], "uncertain": r["uncertain"]}
            for r in reach_rows(g)}
    return {"nodes": nodes, "rels": rels}


def apply_delta(driver, old: dict, new: dict) -> dict:
    """Apply the difference between two `graph_rows` snapshots to the database."""
    t0 = time.time()
    stats = {"nodes_removed": 0, "nodes_added": 0, "nodes_changed": 0,
             "rels_removed": 0, "rels_added": 0, "rels_changed": 0}
    with driver.session() as s:
        # 1. removed nodes
        for label in ("Function", "Class", "Module"):
            gone = [i for i in old["nodes"][label] if i not in new["nodes"][label]]
            _run_batched(s, f"UNWIND $rows AS i MATCH (n:{label} {{id: i}}) DETACH DELETE n", gone)
            stats["nodes_removed"] += len(gone)
        # 2. removed relationships between surviving nodes
        for spec, rows in old["rels"].items():
            typ, a, b = spec
            gone = [{"src": k[0], "dst": k[1], "ctx": k[2] if len(k) > 2 else None}
                    for k in rows if k not in new["rels"].get(spec, {})
                    and k[0] in new["nodes"][a] and k[1] in new["nodes"][b]]
            if gone:
                ctx = " AND r.context = x.ctx" if typ == "IMPORTS" else ""
                _run_batched(s, f"UNWIND $rows AS x MATCH (a:{a} {{id: x.src}})-[r:{typ}]->(b:{b} {{id: x.dst}}) "
                                f"WHERE true{ctx} DELETE r", gone)
            stats["rels_removed"] += sum(1 for k in rows if k not in new["rels"].get(spec, {}))
        # 3. changed nodes, 4. added nodes
        for label in ("Module", "Class", "Function"):
            o, n = old["nodes"][label], new["nodes"][label]
            changed = [r for i, r in n.items() if i in o and o[i] != r]
            added = [r for i, r in n.items() if i not in o]
            extra = ("REMOVE n:Test FOREACH (_ IN CASE WHEN r.is_test THEN [1] ELSE [] END | SET n:Test)"
                     if label == "Function" else "")
            _run_batched(s, f"UNWIND $rows AS r MATCH (n:{label} {{id: r.id}}) SET n = r {extra}", changed)
            _run_batched(s, f"UNWIND $rows AS r CREATE (n:{label}) SET n = r" + (
                " FOREACH (_ IN CASE WHEN r.is_test THEN [1] ELSE [] END | SET n:Test)" if label == "Function" else ""),
                         added)
            stats["nodes_changed"] += len(changed)
            stats["nodes_added"] += len(added)
        # 5. added rels, 6. changed rel props
        for spec, rows in new["rels"].items():
            typ, a, b = spec
            o = old["rels"].get(spec, {})
            added = [{"src": k[0], "dst": k[1], "p": p} for k, p in rows.items() if k not in o]
            changed = [{"src": k[0], "dst": k[1], "ctx": k[2] if len(k) > 2 else None, "p": p}
                       for k, p in rows.items() if k in o and o[k] != p]
            _run_batched(s, f"UNWIND $rows AS x MATCH (a:{a} {{id: x.src}}) MATCH (b:{b} {{id: x.dst}}) "
                            f"CREATE (a)-[r:{typ}]->(b) SET r = x.p", added)
            if changed:
                ctx = " AND r.context = x.ctx" if typ == "IMPORTS" else ""
                _run_batched(s, f"UNWIND $rows AS x MATCH (a:{a} {{id: x.src}})-[r:{typ}]->(b:{b} {{id: x.dst}}) "
                                f"WHERE true{ctx} SET r = x.p", changed)
            stats["rels_added"] += len(added)
            stats["rels_changed"] += len(changed)
    stats["delta_s"] = round(time.time() - t0, 3)
    return stats


def db_signature(driver) -> dict:
    """Order-independent fingerprint of everything in the database (used to prove delta == full load)."""
    import hashlib
    sig = {}
    with driver.session() as s:
        q = {
            "functions": "MATCH (n:Function) WHERE NOT n:Ghost RETURN n.id AS id, n.logic_hash AS h, n.signature_hash AS sh, "
                         "n.test_label AS l, n.test_count AS c, n.test_min_depth AS d, n.test_path AS p, n.start AS s, "
                         "n.is_test AS t, labels(n) AS lb, n.unresolved_calls AS u",
            "classes": "MATCH (n:Class) RETURN n.id AS id, n.start AS s, n.end AS e, n.bases_raw AS b",
            "modules": "MATCH (n:Module) RETURN n.id AS id, n.name AS nm, n.package AS pk, n.partial AS pt",
            "calls": "MATCH (a)-[r:CALLS]->(b) WHERE r.via <> 'removed' OR r.via IS NULL RETURN a.id AS a, b.id AS b, "
                     "r.tier AS t, r.via AS v, r.lines AS l, r.count AS c, r.candidates AS cd",
            "reaches": "MATCH (a)-[r:REACHES]->(b) RETURN a.id AS a, b.id AS b, r.depth AS d, r.uncertain AS u, r.path AS p",
            "structure": "MATCH (a)-[r:CONTAINS|HAS_METHOD|INHERITS|OVERRIDES]->(b) RETURN type(r) AS t, a.id AS a, b.id AS b",
            "imports": "MATCH (a)-[r:IMPORTS]->(b) RETURN a.id AS a, b.id AS b, r.context AS c, r.names AS n",
        }
        for name, cypher in q.items():
            rows = sorted(repr(tuple(sorted((k, repr(v)) for k, v in r.items()))) for r in s.run(cypher).data())
            sig[name] = {"n": len(rows), "md5": hashlib.md5("\n".join(rows).encode()).hexdigest()}
    return sig

