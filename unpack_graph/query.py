"""Indexed queries over a built graph.

`GraphIndex(g)` makes one pass over the nodes and edges and builds dictionaries keyed by name,
qualified name, path, class, base, override and test.  Each query then reads only the entries it
returns, so a query costs microseconds, not a scan of the graph.  The build is paid once per graph.

Results are plain dicts and lists (JSON-ready).  Nothing here changes the graph.
"""
from __future__ import annotations

import time
from collections import defaultdict

from .model import TIER_RANK


def _edge_row(other: str, e) -> dict:
    return {"id": other, "tier": e.tier, "via": e.via, "line": e.line, "lines": list(e.lines),
            "count": e.count, "raw": e.raw, "candidates": list(e.candidates)}


class GraphIndex:
    def __init__(self, g):
        t0 = time.perf_counter()
        self.g = g
        self.by_name: dict = defaultdict(list)
        self.by_qualname: dict = defaultdict(list)
        self.by_path: dict = defaultdict(list)
        self.classes_by_name: dict = defaultdict(list)
        self.methods_of: dict = defaultdict(list)
        self.bases_of: dict = defaultdict(list)
        self.subclasses_of: dict = defaultdict(list)
        self.overrides_of: dict = defaultdict(list)
        self.overridden_by: dict = defaultdict(list)
        self.tests_of: dict = defaultdict(list)            # fid -> [(depth, test)], reached on a static path
        self.uncertain_tests_of: dict = defaultdict(list)  # fid -> [(depth, test)], only through ambiguous edges
        self.untested: list = []                           # production functions labelled none

        for f in g.funcs.values():
            self.by_name[f.name].append(f.id)
            self.by_qualname[f.qualname].append(f.id)
            self.by_path[f.path].append(f.id)
            if f.class_id is not None:
                self.methods_of[f.class_id].append(f.id)
            if not f.is_test and g.reach[f.id].label == "none":
                self.untested.append(f.id)
        for c in g.classes.values():
            self.classes_by_name[c.name].append(c.id)
        for child, parent in g.inherits:
            self.bases_of[child].append(parent)
            self.subclasses_of[parent].append(child)
        for m, o in g.overrides:
            self.overrides_of[m].append(o)
            self.overridden_by[o].append(m)
        for tid, seen in g.reach_pairs.items():
            for fid, ent in seen.items():
                if fid != tid and ent[0] > 0:
                    self.tests_of[fid].append((ent[0], tid))
        for tid, seen in g.reach_pairs_loose.items():
            strict = g.reach_pairs.get(tid, {})
            for fid, ent in seen.items():
                if fid != tid and ent[0] > 0 and fid not in strict:
                    self.uncertain_tests_of[fid].append((ent[0], tid))
        for table in (self.by_name, self.by_qualname, self.by_path, self.classes_by_name, self.methods_of,
                      self.bases_of, self.subclasses_of, self.overrides_of, self.overridden_by,
                      self.tests_of, self.uncertain_tests_of):
            for v in table.values():
                v.sort()
        self.untested.sort()
        self.build_s = round(time.perf_counter() - t0, 4)

    # ------------------------------------------------------------------ lookup

    def find(self, text: str, limit: int = 20) -> list:
        """Ids matching `text`: exact id, then exact qualified name, exact name, then substring."""
        g = self.g
        if text in g.funcs or text in g.classes:
            return [text]
        out = list(self.by_qualname.get(text, [])) + list(self.by_name.get(text, []))
        out += list(self.classes_by_name.get(text, []))
        if not out:
            needle = text.lower()
            for name, ids in self.by_qualname.items():
                if needle in name.lower():
                    out.extend(ids)
                    if len(out) >= limit:
                        break
        seen, res = set(), []
        for x in out:
            if x not in seen:
                seen.add(x)
                res.append(x)
        return res[:limit]

    def node(self, fid: str) -> dict:
        g = self.g
        if fid in g.classes:
            c = g.classes[fid]
            return {"kind": "class", "id": c.id, "name": c.name, "qualname": c.qualname, "path": c.path,
                    "start": c.start, "end": c.end, "bases": list(c.bases_raw),
                    "methods": len(self.methods_of.get(fid, []))}
        f = g.funcs[fid]
        ri = g.reach[fid]
        return {"kind": "function", "id": f.id, "name": f.name, "qualname": f.qualname, "path": f.path,
                "start": f.start, "end": f.end, "is_test": f.is_test, "is_method": f.is_method,
                "is_property": f.is_property, "is_async": f.is_async, "class_id": f.class_id,
                "signature": f.signature, "decorators": list(f.decorators),
                "label": ri.label, "reached_by": len(self.tests_of.get(fid, [])),
                "uncertain_reached_by": len(self.uncertain_tests_of.get(fid, [])),
                "unresolved_sites": len(g.unresolved.get(fid, []))}

    def callers(self, fid: str, production_only: bool = True) -> list:
        g = self.g
        rows = []
        for e in g.in_adj.get(fid, []):
            if "::" not in e.src or e.src == fid:
                continue
            if production_only and g.mods[g.funcs[e.src].path].is_test:
                continue
            rows.append(_edge_row(e.src, e))
        rows.sort(key=lambda r: (TIER_RANK[r["tier"]], r["id"]))
        return rows

    def callees(self, fid: str, production_only: bool = True) -> list:
        g = self.g
        rows = []
        for e in g.out_adj.get(fid, []):
            if e.dst == fid:
                continue
            if production_only and g.mods[g.funcs[e.dst].path].is_test:
                continue
            rows.append(_edge_row(e.dst, e))
        rows.sort(key=lambda r: (TIER_RANK[r["tier"]], r["id"]))
        return rows

    def tests_for(self, fid: str, include_uncertain: bool = False, limit: int | None = None) -> list:
        strict = [{"test": t, "depth": d, "uncertain": False} for d, t in self.tests_of.get(fid, [])]
        out = strict
        if include_uncertain:
            out = strict + [{"test": t, "depth": d, "uncertain": True}
                            for d, t in self.uncertain_tests_of.get(fid, [])]
        return out[:limit] if limit else out

    def overrides(self, fid: str) -> dict:
        return {"overrides": list(self.overrides_of.get(fid, [])),
                "overridden_by": list(self.overridden_by.get(fid, []))}

    def class_info(self, cid: str) -> dict:
        g = self.g
        if cid not in g.classes:
            return {}
        c = g.classes[cid]
        return {"id": cid, "name": c.name, "path": c.path, "bases": list(self.bases_of.get(cid, [])),
                "subclasses": list(self.subclasses_of.get(cid, [])),
                "methods": [{"id": m, "name": g.funcs[m].name, "label": g.reach[m].label}
                            for m in self.methods_of.get(cid, [])]}

    def unresolved(self, fid: str) -> list:
        return [{"line": ln, "raw": raw, "reason": why} for ln, raw, why in self.g.unresolved.get(fid, [])]

    def untested_in(self, path_prefix: str = "", limit: int | None = None) -> list:
        ids = [fid for fid in self.untested if self.g.funcs[fid].path.startswith(path_prefix)]
        return ids[:limit] if limit else ids

    def in_path(self, path: str) -> list:
        """Functions defined in one file (exact path)."""
        return list(self.by_path.get(path, []))
