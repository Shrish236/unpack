"""Change detection between two git revisions (function-level, hash-classified)."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from typing import Optional

from .graph import Graph, build_graph
from .source import GitSource


@dataclass
class Change:
    id: str                       # head id (base id for deleted)
    kind: str                     # added | deleted | modified | renamed | moved
    flags: list = field(default_factory=list)   # text_only | signature | functional
    path: str = ""
    qualname: str = ""
    start: int = 0
    end: int = 0
    head_lines: list = field(default_factory=list)   # [[a, b], ...] in head coordinates
    base_lines: list = field(default_factory=list)   # [[a, b], ...] in base coordinates
    old_id: Optional[str] = None
    still_called_by: list = field(default_factory=list)   # deleted: base callers that remain in head
    callers_in_base: list = field(default_factory=list)

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        return d


@dataclass
class ChangeSet:
    base: str
    head: str
    files: list = field(default_factory=list)          # [(status, old_path, new_path)]
    functions: list = field(default_factory=list)      # [Change]
    classes: list = field(default_factory=list)        # [{id, kind, ...}]
    modules: list = field(default_factory=list)        # [{path, module_level_changed, partial...}]
    base_graph: Optional[Graph] = None
    head_graph: Optional[Graph] = None

    def to_dict(self) -> dict:
        return {"base": self.base, "head": self.head,
                "files": [list(f) for f in self.files],
                "functions": [c.to_dict() for c in self.functions],
                "classes": self.classes, "modules": self.modules}


def _git(root: str, *args: str) -> str:
    return subprocess.run(["git", "-C", root, *args], check=True, capture_output=True).stdout.decode(
        "utf-8", "replace")


def name_status(root: str, base: str, head: str) -> list:
    out = _git(root, "diff", "--name-status", "-M", "-z", base, head).split("\0")
    res, i = [], 0
    while i < len(out) and out[i]:
        st = out[i]
        if st[0] in ("R", "C"):
            res.append((st[0], out[i + 1], out[i + 2]))
            i += 3
        else:
            res.append((st[0], out[i + 1], out[i + 1]))
            i += 2
    return res


_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def diff_hunks(root: str, base: str, head: str) -> dict:
    """{(old_path, new_path): [(a, b, c, d)]} from `git diff -U0 -M`."""
    out = _git(root, "diff", "-U0", "-M", "--no-color", base, head)
    res: dict = {}
    old = new = None
    for line in out.split("\n"):
        if line.startswith("--- "):
            old = line[4:].strip()
            old = old[2:] if old.startswith("a/") else None
        elif line.startswith("+++ "):
            new = line[4:].strip()
            new = new[2:] if new.startswith("b/") else None
            res.setdefault((old, new), [])
        elif line.startswith("@@"):
            m = _HUNK.match(line)
            if m:
                a = int(m.group(1))
                b = int(m.group(2)) if m.group(2) is not None else 1
                c = int(m.group(3))
                d = int(m.group(4)) if m.group(4) is not None else 1
                res[(old, new)].append((a, b, c, d))
    return res


def _clip(ranges: list, start: int, end: int) -> list:
    out = []
    for a, b in ranges:
        lo, hi = max(a, start), min(b, end)
        if lo <= hi:
            out.append([lo, hi])
    return out


def _flags(b, h) -> list:
    flags = []
    if b.signature_hash != h.signature_hash:
        flags.append("signature")
    if b.logic_hash != h.logic_hash:
        flags.append("functional")
    if not flags and (b.body_hash != h.body_hash or b.text_hash != h.text_hash):
        flags.append("text_only")
    return flags


def detect_changes(root: str, base: str, head: str, base_graph: Optional[Graph] = None,
                   head_graph: Optional[Graph] = None, resolver_opts: Optional[dict] = None) -> ChangeSet:
    cs = ChangeSet(base, head)
    cs.files = name_status(root, base, head)
    gb = base_graph or build_graph(GitSource(root, base), resolver_opts)
    gh = head_graph or build_graph(GitSource(root, head), resolver_opts)
    cs.base_graph, cs.head_graph = gb, gh
    hunks = diff_hunks(root, base, head)

    def by_path(g: Graph, path: str) -> dict:
        m = g.mods.get(path)
        return {f.id: f for f in m.funcs} if m else {}

    added, deleted, modified = {}, {}, []
    for st, op, np_ in cs.files:
        if not (op.endswith(".py") or np_.endswith(".py")):
            continue
        if st == "A" or st == "C":
            added.update(by_path(gh, np_))
        elif st == "D":
            deleted.update(by_path(gb, op))
        else:                       # M or R
            bf, hf = by_path(gb, op), by_path(gh, np_)
            if op != np_:           # file renamed: match by qualname inside the pair
                bf = {f.qualname + "|" + (f.id.split("#", 1)[1] if "#" in f.id else ""): f for f in bf.values()}
                hf = {f.qualname + "|" + (f.id.split("#", 1)[1] if "#" in f.id else ""): f for f in hf.values()}
            for k, hfun in hf.items():
                bfun = bf.get(k)
                if bfun is None:
                    added[hfun.id] = hfun
                else:
                    modified.append((bfun, hfun, op != np_))
            for k, bfun in bf.items():
                if k not in hf:
                    deleted[bfun.id] = bfun
        # module-level (non-function) changes + class changes
        bm, hm = gb.mods.get(op), gh.mods.get(np_)
        info = {"path": np_ if hm else op, "status": st, "old_path": op if op != np_ else None}
        if bm and hm:
            info["module_level_changed"] = bm.logic_hash != hm.logic_hash
            bcl = {c.qualname: c for c in bm.classes}
            for c in hm.classes:
                o = bcl.get(c.qualname)
                if o is None:
                    cs.classes.append({"id": c.id, "kind": "added", "path": c.path, "start": c.start, "end": c.end})
                else:
                    flags = []
                    if o.bases_raw != c.bases_raw or o.decorators != c.decorators:
                        flags.append("signature")
                    if o.logic_hash != c.logic_hash:
                        flags.append("functional")
                    if not flags and o.doc_hash != c.doc_hash:
                        flags.append("text_only")
                    if flags:
                        cs.classes.append({"id": c.id, "kind": "modified", "flags": flags, "path": c.path,
                                           "start": c.start, "end": c.end, "bases_before": o.bases_raw,
                                           "bases_after": c.bases_raw})
            hcl = {c.qualname for c in hm.classes}
            for c in bm.classes:
                if c.qualname not in hcl:
                    cs.classes.append({"id": c.id, "kind": "deleted", "path": c.path, "start": c.start, "end": c.end})
        else:
            info["module_level_changed"] = True
        info["partial_head"] = bool(hm and hm.partial)
        cs.modules.append(info)

    changes: list = []
    for bfun, hfun, filemoved in modified:
        flags = _flags(bfun, hfun)
        if not flags and not filemoved:
            continue
        c = Change(hfun.id, "modified", flags, hfun.path, hfun.qualname, hfun.start, hfun.end)
        if filemoved:
            c.old_id = bfun.id
            if not flags:
                c.kind = "moved"
            else:
                c.kind = "modified"
        changes.append(c)

    # simple renames / moves: one deleted + one added with identical logic, unique on both sides
    def key(f):
        return f.logic_hash
    dcount: dict = {}
    acount: dict = {}
    for f in deleted.values():
        dcount.setdefault(key(f), []).append(f)
    for f in added.values():
        acount.setdefault(key(f), []).append(f)
    paired_d, paired_a = set(), set()
    for k, ds in dcount.items():
        a_s = acount.get(k, [])
        if len(ds) == 1 and len(a_s) == 1:
            d, a = ds[0], a_s[0]
            if d.path == a.path and d.name == a.name:
                continue
            c = Change(a.id, "renamed" if d.path == a.path else "moved",
                       [] if d.signature_hash == a.signature_hash or d.name != a.name else ["signature"],
                       a.path, a.qualname, a.start, a.end, old_id=d.id)
            changes.append(c)
            paired_d.add(d.id)
            paired_a.add(a.id)
    for f in added.values():
        if f.id not in paired_a:
            changes.append(Change(f.id, "added", [], f.path, f.qualname, f.start, f.end))
    for f in deleted.values():
        if f.id not in paired_d:
            callers = sorted(e.src for e in gb.in_adj.get(f.id, []) if "::" in e.src and e.src not in deleted)
            c = Change(f.id, "deleted", [], f.path, f.qualname, f.start, f.end, callers_in_base=callers)
            # callers that still exist in head and still contain a call to that name
            for caller in callers:
                hf = gh.funcs.get(caller)
                if hf is None:
                    continue
                for site in hf.calls:
                    if site.shape.last() == f.name:
                        c.still_called_by.append(caller)
                        break
            changes.append(c)

    # attach changed line ranges
    for c in changes:
        for (op, np_), hs in hunks.items():
            if c.kind == "deleted":
                if op != c.path:
                    continue
                for a, b, _c, _d in hs:
                    if b > 0:
                        c.base_lines += _clip([(a, a + b - 1)], c.start, c.end)
                c.head_lines = []
                continue
            if np_ != c.path:
                continue
            hr, br = [], []
            for a, b, cc, d in hs:
                if d > 0:
                    hr.append((cc, cc + d - 1))
                else:
                    hr.append((cc, cc))          # pure deletion: point just after line cc
                if b > 0:
                    br.append((a, a + b - 1))
            c.head_lines += _clip(hr, c.start, c.end)
            old = c.old_id and gb.funcs.get(c.old_id)
            bfun = old or gb.funcs.get(c.id)
            if bfun is not None and (op == np_ or c.old_id):
                c.base_lines += _clip(br, bfun.start, bfun.end)
    changes.sort(key=lambda c: (c.path, c.start, c.id))
    cs.functions = changes
    return cs
