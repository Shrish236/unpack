"""Pass 2: whole-repo name, type and call resolution.

Values are small tuples ("entities") wrapped in `V` together with a confidence tier:

  ("mod", dotted)   in-repo module          ("ext", name)   something outside the repo
  ("cls", cid)      class object            ("inst", cid)   instance of repo class
  ("fn", fid)       function / bound method ("super", cid)  super() inside cid
  ("cm", cid)       @contextmanager result  ("var", (path, name)) module variable
  ("unk",)          no information (unique-name fallback allowed)
  ("miss", cid)     typed receiver that has no such attribute (never guessed)
  ("opaque",)       known attribute whose value we cannot type (never guessed)
"""
from __future__ import annotations

import ast
import builtins
import sys
from dataclasses import dataclass, field
from typing import Optional

from .model import (TIER_AMBIGUOUS, TIER_EXTRACTED, TIER_INFERRED, TIER_RANK, CallSite, FuncInfo, ModuleInfo, Shape)

MAX_REEXPORT_HOPS = 3
BUILTIN_NAMES = set(dir(builtins))
STDLIB = set(getattr(sys, "stdlib_module_names", ()))
BUILTIN_METHOD_NAMES = set()
for _t in (str, bytes, bytearray, dict, list, set, frozenset, tuple, int, float, object, memoryview):
    BUILTIN_METHOD_NAMES |= {n for n in dir(_t) if not n.startswith("__")}
# very common file-/stream-/lock-like method names that stdlib objects provide
BUILTIN_METHOD_NAMES |= {"read", "write", "close", "flush", "seek", "tell", "readline", "readlines",
                         "acquire", "release", "wait", "set", "is_set", "put", "get_nowait", "send",
                         "recv", "connect", "run", "start", "stop", "cancel", "result", "done",
                         "add_done_callback", "submit", "shutdown", "join", "match", "search",
                         "group", "groups", "sub", "split", "findall", "isoformat", "strftime"}

UNWRAP_ITER = {"Iterator", "Generator", "AsyncIterator", "AsyncGenerator", "Iterable",
               "AsyncIterable", "ContextManager", "AsyncContextManager"}
SEQ_NAMES = {"list", "List", "Sequence", "MutableSequence", "Iterable", "Iterator", "Set", "set",
             "frozenset", "FrozenSet", "Collection", "Deque", "deque", "Tuple", "tuple", "AsyncIterator",
             "AsyncIterable", "Generator", "AsyncGenerator", "dict", "Dict", "Mapping", "MutableMapping",
             "DefaultDict", "OrderedDict", "AbstractSet", "MutableSet"}
MAP_NAMES = {"dict", "Dict", "Mapping", "MutableMapping", "DefaultDict", "OrderedDict"}
SEQ_BUILTINS = {"list", "tuple", "set", "frozenset", "sorted", "reversed", "iter"}
TRANSPARENT = {"Annotated", "ClassVar", "Final", "Required", "NotRequired", "Awaitable", "Coroutine"}


@dataclass(frozen=True)
class V:
    ent: tuple
    tier: str = TIER_EXTRACTED
    via: Optional[str] = None
    nodisp: bool = False


def worse(a: str, b: str) -> str:
    return a if TIER_RANK[a] >= TIER_RANK[b] else b


def adj(v: V, tier: str = None, via: str = None, nodisp: bool = None) -> V:
    t = worse(v.tier, tier) if tier else v.tier
    vi = v.via
    if via and (vi is None or vi == "type"):
        vi = via
    return V(v.ent, t, vi, v.nodisp if nodisp is None else nodisp)


UNK = V(("unk",))


@dataclass
class Target:
    fid: str
    tier: str
    via: Optional[str] = None


@dataclass
class SiteRes:
    kind: str                 # call | property | with | ref
    path: str
    line: int
    col: int
    raw: str
    owner: str
    shape_cat: str
    status: str               # resolved | ambiguous | unresolved | external | builtin | no_init
    targets: list = field(default_factory=list)
    candidates: list = field(default_factory=list)
    reason: str = ""
    guards: tuple = ()
    kwargs: tuple = ()
    npos: int = 0
    splat: bool = False


@dataclass
class Scope:
    mod: ModuleInfo
    func: Optional[FuncInfo] = None


class Resolver:
    def __init__(self, mods: dict, enable_ref_edges: bool = True, builtin_guard: bool = True):
        self.mods = mods
        self.enable_ref_edges = enable_ref_edges
        self.builtin_guard = builtin_guard
        self.mod_by_name: dict = {}
        self.funcs: dict = {}
        self.classes: dict = {}
        self.members: dict = {}        # cid -> {name: [FuncInfo]}
        self.nested_cls: dict = {}     # cid -> {name: cid}
        self.methods_by_name: dict = {}
        self.fixtures: dict = {}       # path -> {name: FuncInfo}
        self.class_fixtures: dict = {}  # cid -> {name: FuncInfo}
        self._bases: dict = {}
        self._extbase: dict = {}
        self._children: dict = {}
        self._mro: dict = {}
        self._modsym: dict = {}
        self._imp_bind: dict = {}
        self._local_types: dict = {}
        self._active: set = set()
        self._attr_types: dict = {}
        self._ann_cache: dict = {}
        self._emit: list = []
        self._caller_is_test = True
        for m in mods.values():
            if m.name not in self.mod_by_name or m.is_init:
                self.mod_by_name[m.name] = m
        for m in mods.values():
            for f in m.funcs:
                self.funcs[f.id] = f
                if f.class_id:
                    self.members.setdefault(f.class_id, {}).setdefault(f.name, []).append(f)
                    if not f.is_property:
                        self.methods_by_name.setdefault(f.name, []).append(f)
                if f.is_fixture:
                    nm = f.fixture_name or f.name
                    if f.class_id:
                        self.class_fixtures.setdefault(f.class_id, {})[nm] = f
                    elif not f.parent_func:
                        self.fixtures.setdefault(m.path, {})[nm] = f
            for c in m.classes:
                self.classes[c.id] = c
                if c.parent_class:
                    self.nested_cls.setdefault(c.parent_class, {})[c.name] = c.id

    # ------------------------------------------------------------- modules
    def abs_module(self, mod: ModuleInfo, level: int, module: str) -> str:
        if level == 0:
            return module
        parts = mod.package.split(".") if mod.package else []
        up = level - 1
        parts = parts[: len(parts) - up] if up <= len(parts) else []
        if up > len(mod.package.split(".") if mod.package else []):
            return ""
        return ".".join(parts + ([module] if module else []))

    def find_module(self, importer: ModuleInfo, dotted: str, level: int = 0) -> Optional[ModuleInfo]:
        if not dotted:
            return None
        m = self.mod_by_name.get(dotted)
        if m is None and level == 0 and dotted.split(".")[0] not in STDLIB and importer.package:
            # absolute import that only works because an ancestor directory is on sys.path
            # (pytest rootdir/conftest style: `from conftest import X` inside tests/)
            parts = importer.package.split(".")
            for i in range(len(parts), 0, -1):
                m = self.mod_by_name.get(".".join(parts[:i]) + "." + dotted)
                if m is not None:
                    return m
            return None
        if m is None:
            return None
        if level == 0 and "." not in m.name and not m.is_init and m.name.split(".")[0] in STDLIB:
            # a loose top-level file that merely shares its name with a stdlib module
            if importer.path.rsplit("/", 1)[0] != m.path.rsplit("/", 1)[0]:
                return None
        return m

    def import_bindings(self, mod: ModuleInfo) -> dict:
        b = self._imp_bind.get(mod.path)
        if b is not None:
            return b
        b = {}
        for rec in mod.imports:
            if rec.scope:
                continue
            self._bind_import(mod, rec, b)
        self._imp_bind[mod.path] = b
        return b

    def _bind_import(self, mod, rec, b):
        if rec.kind == "import":
            for nm, al in rec.names:
                if al:
                    b[al] = ("module", nm, 0, rec.try_guard)
                else:
                    top = nm.split(".")[0]
                    b[top] = ("module", top, 0, rec.try_guard)
        else:
            absm = self.abs_module(mod, rec.level, rec.module)
            for nm, al in rec.names:
                b[al or nm] = ("from", absm, nm, rec.level, rec.try_guard)

    def resolve_binding(self, mod, bd, hops) -> Optional[tuple]:
        if bd[0] == "module":
            m = self.find_module(mod, bd[1])
            return ("mod", m.name) if m else ("ext", bd[1])
        _, absm, nm, level = bd[:4]
        tm = self.find_module(mod, absm, level) if absm else None
        if tm is None:
            if absm == "" and level > 0:
                return ("opaque",)
            sub = (absm + "." + nm) if absm else nm
            sm = self.find_module(mod, sub, level)
            if sm:
                return ("mod", sm.name)
            return ("ext", f"{absm}.{nm}")
        if hops >= MAX_REEXPORT_HOPS:
            return ("opaque",)
        if tm is mod:                       # `from . import sub` inside pkg/__init__.py: the submodule
            sub = tm.name + "." + nm
            return ("mod", sub) if sub in self.mod_by_name else ("opaque",)
        sym = self.mod_symbol(tm, nm, hops + 1)
        if sym is not None:
            return sym
        sub = tm.name + "." + nm
        if sub in self.mod_by_name:
            return ("mod", sub)
        return ("opaque",)

    def exports(self, m: ModuleInfo) -> set:
        if m.all_names is not None:
            return set(m.all_names)
        out = {n for n in m.top_defs if not n.startswith("_")}
        out |= {n for n in self.import_bindings(m) if not n.startswith("_")}
        out |= {n for n in m.local_names if not n.startswith("_")}
        return out

    def mod_symbol(self, mod: ModuleInfo, name: str, hops: int = 0) -> Optional[tuple]:
        key = (mod.path, name, hops)
        if key in self._modsym:
            return self._modsym[key]
        self._modsym[key] = None   # cycle guard
        res = None
        td = mod.top_defs.get(name)
        bd0 = self.import_bindings(mod).get(name)
        if td is not None:
            res = ("fn" if td[0] == "func" else "cls", td[1])
            if bd0 is not None and bd0[-1]:
                # `try: from x import name / except ImportError: def name(): ...` -> prefer the import
                alt = self.resolve_binding(mod, bd0, hops)
                if alt is not None and alt[0] in ("fn", "cls", "mod"):
                    res = alt
        else:
            bd = self.import_bindings(mod).get(name)
            if bd is not None:
                res = self.resolve_binding(mod, bd, hops)
            else:
                if hops < MAX_REEXPORT_HOPS:
                    for rec in reversed(mod.imports):
                        if rec.scope or not rec.star:
                            continue
                        absm = self.abs_module(mod, rec.level, rec.module)
                        tm = self.find_module(mod, absm, rec.level)
                        if tm is not None and tm is not mod:
                            if name in self.exports(tm):
                                res = self.mod_symbol(tm, name, hops + 1)
                                if res is not None:
                                    break
                if res is None and name in mod.local_names:
                    res = ("var", (mod.path, name))
        self._modsym[key] = res
        return res

    def has_unresolved_star(self, mod: ModuleInfo) -> bool:
        for rec in mod.imports:
            if rec.star and not rec.scope:
                absm = self.abs_module(mod, rec.level, rec.module)
                if self.find_module(mod, absm, rec.level) is None:
                    return True
        return False

    # ------------------------------------------------------------- classes
    def class_mod(self, cid: str) -> ModuleInfo:
        return self.mods[self.classes[cid].path]

    def class_expr(self, text: str, mod: ModuleInfo) -> Optional[tuple]:
        try:
            node = ast.parse(text.strip(), mode="eval").body
        except SyntaxError:
            return None
        if isinstance(node, ast.Subscript):
            node = node.value
        if isinstance(node, ast.Call):
            node = node.func
        parts = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if not isinstance(node, ast.Name):
            return None
        parts.append(node.id)
        parts.reverse()
        ent = self._module_chain(mod, parts)
        return ent

    def _module_chain(self, mod: ModuleInfo, parts: list) -> Optional[tuple]:
        sym = self.mod_symbol(mod, parts[0], 0)
        if sym is None:
            return ("ext", ".".join(parts)) if parts[0] in BUILTIN_NAMES else None
        ent = sym
        for p in parts[1:]:
            if ent[0] == "mod":
                m = self.mod_by_name[ent[1]]
                s2 = self.mod_symbol(m, p, 0)
                if s2 is None:
                    sub = ent[1] + "." + p
                    s2 = ("mod", sub) if sub in self.mod_by_name else ("opaque",)
                ent = s2
            elif ent[0] == "cls":
                nc = self.nested_cls.get(ent[1], {}).get(p)
                ent = ("cls", nc) if nc else ("opaque",)
            elif ent[0] == "ext":
                ent = ("ext", ent[1] + "." + p)
            else:
                return ("opaque",)
        return ent

    def bases(self, cid: str) -> list:
        if cid in self._bases:
            return self._bases[cid]
        self._bases[cid] = []
        c = self.classes[cid]
        mod = self.class_mod(cid)
        out, ext = [], False
        for raw in c.bases_raw:
            ent = self.class_expr(raw, mod)
            if ent is not None and ent[0] == "var":
                ent = None
            if ent is not None and ent[0] == "cls":
                if ent[1] != cid:
                    out.append(ent[1])
            else:
                ext = True
        self._bases[cid] = out
        self._extbase[cid] = ext
        return out

    def mro(self, cid: str) -> list:
        if cid in self._mro:
            return self._mro[cid]
        self._mro[cid] = [cid]
        order = [cid]
        for b in self.bases(cid):
            for x in self.mro(b):
                if x not in order:
                    order.append(x)
        self._mro[cid] = order
        return order

    ENUM_BASES = {"Enum", "IntEnum", "StrEnum", "Flag", "IntFlag", "ReprEnum"}

    def is_enum(self, cid: str) -> bool:
        for c in self.mro(cid):
            for raw in self.classes[c].bases_raw:
                if raw.split("[")[0].split(".")[-1] in self.ENUM_BASES:
                    return True
        return False

    def has_ext_base(self, cid: str) -> bool:
        for c in self.mro(cid):
            self.bases(c)
            if self._extbase.get(c):
                return True
        return False

    def children(self, cid: str) -> list:
        if not self._children:
            for c in self.classes:
                for b in self.bases(c):
                    self._children.setdefault(b, []).append(c)
        return self._children.get(cid, [])

    def descendants(self, cid: str) -> list:
        out, stack, seen = [], list(self.children(cid)), {cid}
        while stack:
            c = stack.pop()
            if c in seen:
                continue
            seen.add(c)
            out.append(c)
            stack.extend(self.children(c))
        return out

    def pick_func(self, funcs: list, want_setter: bool = False) -> Optional[FuncInfo]:
        cands = [f for f in funcs if f.is_setter == want_setter and not f.id.endswith("#deleter")]
        if not cands and want_setter:
            return None
        if not cands:
            cands = funcs
        non_ov = [f for f in cands if not f.is_overload]
        cands = non_ov or cands
        return max(cands, key=lambda f: f.start) if cands else None

    def find_member(self, order: list, attr: str):
        """First class in `order` that defines `attr` -> ('fn', owner, [funcs]) | ('cls', owner, cid)."""
        for c in order:
            fs = self.members.get(c, {}).get(attr)
            if fs:
                return ("fn", c, fs)
            nc = self.nested_cls.get(c, {}).get(attr)
            if nc:
                return ("cls", c, nc)
        return None

    # --------------------------------------------------------- annotations
    def ann_types(self, text: Optional[str], mod: ModuleInfo, cid: Optional[str] = None,
                  unwrap_iter: bool = False, as_cm: bool = False) -> list:
        if not text:
            return []
        key = (text, mod.path, cid, unwrap_iter, as_cm)
        if key in self._ann_cache:
            return self._ann_cache[key]
        try:
            node = ast.parse(text.strip(), mode="eval").body
        except SyntaxError:
            self._ann_cache[key] = []
            return []
        res = self._ann_node(node, mod, cid, unwrap_iter, as_cm, 0)
        self._ann_cache[key] = res
        return res

    def _ann_node(self, node, mod, cid, unwrap_iter, as_cm, depth) -> list:
        if depth > 12:
            return []
        if isinstance(node, ast.Constant):
            if isinstance(node.value, str):
                try:
                    inner = ast.parse(node.value.strip(), mode="eval").body
                except SyntaxError:
                    return []
                return self._ann_node(inner, mod, cid, unwrap_iter, as_cm, depth + 1)
            return []
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            return (self._ann_node(node.left, mod, cid, unwrap_iter, as_cm, depth + 1)
                    + self._ann_node(node.right, mod, cid, unwrap_iter, as_cm, depth + 1))
        base, args = node, []
        if isinstance(node, ast.Subscript):
            base = node.value
            sl = node.slice
            args = list(sl.elts) if isinstance(sl, ast.Tuple) else [sl]
        parts = []
        b = base
        while isinstance(b, ast.Attribute):
            parts.append(b.attr)
            b = b.value
        if not isinstance(b, ast.Name):
            return []
        parts.append(b.id)
        parts.reverse()
        last = parts[-1]
        if args:
            if last in ("Optional",):
                return self._ann_node(args[0], mod, cid, unwrap_iter, as_cm, depth + 1)
            if last == "Union":
                out = []
                for a in args:
                    out += self._ann_node(a, mod, cid, unwrap_iter, as_cm, depth + 1)
                return out
            if last in TRANSPARENT:
                return self._ann_node(args[0], mod, cid, unwrap_iter, as_cm, depth + 1)
            if last in UNWRAP_ITER and (unwrap_iter or as_cm):
                inner = self._ann_node(args[0], mod, cid, False, False, depth + 1)
                if as_cm:
                    return [V(("cm", v.ent[1]), v.tier, v.via) for v in inner if v.ent[0] == "inst"]
                return inner
        if len(args) == 2 and last in MAP_NAMES:
            ks = self._ann_node(args[0], mod, cid, False, False, depth + 1)
            vs = self._ann_node(args[1], mod, cid, False, False, depth + 1)
            kc = tuple(sorted({v.ent[1] for v in ks if v.ent[0] == "inst"}))
            vc = tuple(sorted({v.ent[1] for v in vs if v.ent[0] == "inst"}))
            if kc or vc:
                return [V(("map", kc, vc), TIER_INFERRED, "type")]
        if args and last in SEQ_NAMES:
            elems = []
            for a in (args if last in ("Tuple", "tuple") else args[:1]):
                elems += self._ann_node(a, mod, cid, False, False, depth + 1)
            cids = tuple(sorted({v.ent[1] for v in elems if v.ent[0] == "inst"}))
            if cids:
                return [V(("seq", cids), TIER_INFERRED, "type")]
        if last == "Self" and cid:
            return [V(("inst", cid), TIER_INFERRED, "type")]
        if len(parts) == 1 and parts[0] in mod.typevars:
            bound = mod.typevars[parts[0]]
            return self.ann_types(bound, mod, cid) if bound else []
        ent = self._module_chain(mod, parts)
        if ent is None:
            return []
        if ent[0] == "cls":
            return [V(("inst", ent[1]), TIER_INFERRED, "type")]
        if ent[0] in ("ext", "mod"):
            return [V(("ext", ".".join(parts)), TIER_INFERRED, "type")]
        return []

    # --------------------------------------------------------- name lookup
    def class_of_func(self, f: Optional[FuncInfo]) -> Optional[str]:
        while f is not None:
            if f.class_id:
                return f.class_id
            f = self.funcs.get(f.parent_func) if f.parent_func else None
        return None

    def lookup_name(self, name: str, sc: Scope) -> list:
        f = sc.func
        while f is not None:
            nd = f.nested_defs.get(name)
            if nd is not None:
                return [V(("fn" if nd[0] == "func" else "cls", nd[1]))]
            if name in f.local_names:
                for rec in f.imports:
                    bd = {}
                    self._bind_import(sc.mod, rec, bd)
                    if name in bd:
                        ent = self.resolve_binding(sc.mod, bd[name], 0)
                        return self._sym_to_vals(ent, sc)
                return self.local_types(f, name) or [UNK]
            f = self.funcs.get(f.parent_func) if f.parent_func else None
        sym = self.mod_symbol(sc.mod, name, 0)
        if sym is not None:
            return self._sym_to_vals(sym, sc)
        if name in BUILTIN_NAMES:
            return [V(("ext", "builtins." + name))]
        if self.has_unresolved_star(sc.mod):
            return [V(("opaque",))]
        return []

    def _sym_to_vals(self, sym: Optional[tuple], sc: Scope) -> list:
        if sym is None:
            return [V(("opaque",))]
        if sym[0] == "var":
            path, nm = sym[1]
            vals = self.module_var(path, nm)
            return vals or [UNK]
        return [V(sym)]

    def module_var(self, path: str, name: str) -> list:
        key = ("var", path, name)
        if key in self._active:
            return []
        if key in self._local_types:
            return self._local_types[key]
        self._active.add(key)
        mod = self.mods[path]
        out = []
        for b in mod.bindings:
            if b.name == name:
                out += self._binding_vals(b, Scope(mod, None), mod, None)
        self._active.discard(key)
        self._local_types[key] = out
        return out

    def _binding_vals(self, b, sc: Scope, mod, f: Optional[FuncInfo]) -> list:
        if b.kind == "ann":
            return self.ann_types(b.ann, mod, self.class_of_func(f))
        if b.kind == "yield":
            # `x = yield y` receives the Generator[Y, SendType, R] send type of the enclosing function
            if f is None or not f.returns:
                return []
            try:
                node = ast.parse(f.returns.strip(), mode="eval").body
            except SyntaxError:
                return []
            if isinstance(node, ast.Subscript):
                sl = node.slice
                args = list(sl.elts) if isinstance(sl, ast.Tuple) else [sl]
                base = node.value
                last = base.attr if isinstance(base, ast.Attribute) else getattr(base, "id", "")
                if last in ("Generator", "AsyncGenerator") and len(args) >= 2:
                    return self._ann_node(args[1], mod, self.class_of_func(f), False, False, 0)
            return []
        if b.kind == "for_unpack":
            saved, self._emit = self._emit, []
            try:
                vals = self.eval_value(b.shape, sc)
            finally:
                self._emit = saved
            out = []
            for v in vals:
                if v.ent[0] == "pairs":
                    cs = v.ent[1] if b.index == 0 else v.ent[2] if b.index == 1 else ()
                    out += [V(("inst", c), TIER_INFERRED, "elem") for c in cs]
            return out
        if b.kind == "for":
            saved, self._emit = self._emit, []
            try:
                vals = self.eval_value(b.shape, sc)
            finally:
                self._emit = saved
            out = []
            for v in vals:
                out += self.elements_of(v)
            return out
        if b.kind in ("val", "with"):
            saved, self._emit = self._emit, []
            try:
                vals = self.eval_value(b.shape, sc)
            finally:
                self._emit = saved
            out = []
            for v in vals:
                if b.kind == "with":
                    out += self._enter_types(v, sc)
                else:
                    out.append(adj(v, TIER_INFERRED, "type"))
            return out
        return []

    def elements_of(self, v: V, index: bool = False) -> list:
        """Element values produced by iterating (or indexing, `index=True`) `v`, when statically known."""
        k = v.ent[0]
        if k == "coll":
            return [V(e, TIER_INFERRED, "table") for e in v.ent[1]]
        if k == "map":
            cs = v.ent[2] if index else v.ent[1]          # d[k] -> value type; iteration -> key type
            return [V(("inst", c), TIER_INFERRED, "elem") for c in cs]
        if k == "seq":
            return [V(("inst", c), TIER_INFERRED, "elem") for c in v.ent[1]]
        if v.ent[0] == "inst":
            hit = self.find_member(self.mro(v.ent[1]), "__iter__")
            if hit and hit[0] == "fn":
                f = self.pick_func(hit[2])
                out = []
                for t in self.return_types(f):
                    if t.ent[0] == "seq":
                        out += [V(("inst", c), TIER_INFERRED, "elem") for c in t.ent[1]]
                return out
        return []

    def return_types(self, f: FuncInfo, **kw) -> list:
        """Declared return types, else (for unannotated functions) types of returned/yielded values."""
        mod = self.mods[f.path]
        ts = self.ann_types(f.returns, mod, f.class_id, **kw)
        if ts or f.returns or not f.return_shapes:
            return ts
        key = ("ret", f.id)
        if key in self._active:
            return []
        if key in self._local_types:
            return self._local_types[key]
        self._active.add(key)
        saved, self._emit = self._emit, []
        out = []
        try:
            sc = Scope(mod, f)
            for sh in f.return_shapes:
                for v in self.eval_value(sh, sc):
                    if v.ent[0] in ("inst", "seq"):
                        out.append(adj(v, TIER_INFERRED, "return"))
        finally:
            self._emit = saved
            self._active.discard(key)
        out = self._dedupe(out)
        if kw.get("as_cm"):
            out = [V(("cm", v.ent[1]), v.tier, v.via) for v in out if v.ent[0] == "inst"]
        self._local_types[key] = out
        return out

    def _enter_types(self, v: V, sc: Scope) -> list:
        k = v.ent[0]
        if k == "cm":
            return [adj(V(("inst", v.ent[1]), v.tier, v.via), TIER_INFERRED, "type")]
        if k == "inst":
            names = ("__enter__",)
            order = self.mro(v.ent[1])
            hit = self.find_member(order, names[0])
            if hit and hit[0] == "fn":
                f = self.pick_func(hit[2])
                ts = self.return_types(f)
                ts = [t for t in ts if t.ent[0] == "inst"]
                if ts:
                    return [adj(t, TIER_INFERRED, "type") for t in ts]
            return [adj(v, TIER_INFERRED, "type")]
        return [adj(v, TIER_INFERRED, "type")]

    def visible_fixture(self, f: FuncInfo, name: str) -> Optional[FuncInfo]:
        if f.class_id and name in self.class_fixtures.get(f.class_id, {}):
            return self.class_fixtures[f.class_id][name]
        path = f.path
        if name in self.fixtures.get(path, {}):
            return self.fixtures[path][name]
        d = path.rsplit("/", 1)[0] if "/" in path else ""
        while True:
            cp = (d + "/" if d else "") + "conftest.py"
            if name in self.fixtures.get(cp, {}):
                return self.fixtures[cp][name]
            if not d:
                break
            d = d.rsplit("/", 1)[0] if "/" in d else ""
        return None

    def local_types(self, f: FuncInfo, name: str) -> list:
        key = (f.id, name)
        if key in self._local_types:
            return self._local_types[key]
        if key in self._active:
            return []
        self._active.add(key)
        mod = self.mods[f.path]
        sc = Scope(mod, f)
        out: list = []
        for b in f.bindings:
            if b.name != name:
                continue
            if b.kind == "param":
                if f.is_method and name == f.first_param and f.params and f.params[0][0] == name:
                    if f.is_classmethod:
                        out.append(V(("cls", f.class_id)))
                    else:
                        out.append(V(("inst", f.class_id)))
                elif b.ann:
                    out += self.ann_types(b.ann, mod, self.class_of_func(f))
                else:
                    fx = self.visible_fixture(f, name) if (mod.is_test) else None
                    if fx is not None and fx is not f:
                        ts = self.return_types(fx, unwrap_iter=True)
                        out += [adj(t, TIER_INFERRED, "fixture") for t in ts if t.ent[0] == "inst"]
            else:
                out += self._binding_vals(b, sc, mod, f)
        self._active.discard(key)
        # dedupe
        seen, res = set(), []
        for v in out:
            k = (v.ent, v.tier, v.via)
            if k not in seen:
                seen.add(k)
                res.append(v)
        self._local_types[key] = res
        return res

    # ------------------------------------------------------- attribute types
    def attr_types(self, cid: str, attr: str) -> Optional[list]:
        """Types of instance attribute `attr`, or None if the class chain never mentions it."""
        key = (cid, attr)
        if key in self._attr_types:
            return self._attr_types[key]
        if key in self._active:
            return []
        self._active.add(key)
        result = None
        for c in self.mro(cid):
            cls = self.classes[c]
            cm = self.class_mod(c)
            found = False
            out: list = []
            if attr in cls.attr_anns:
                found = True
                out += self.ann_types(cls.attr_anns[attr], cm, c)
            for ab in cls.attr_bindings:
                if ab.attr == attr:
                    found = True
                    out += self._attr_binding_vals(ab, Scope(cm, None), cm, c)
            meths = [f for fs in self.members.get(c, {}).values() for f in fs]
            meths.sort(key=lambda f: (f.name != "__init__", f.start))
            for m in meths:
                for ab in m.attr_bindings:
                    if ab.attr == attr:
                        found = True
                        out += self._attr_binding_vals(ab, Scope(cm, m), cm, c)
            if found:
                seen, res = set(), []
                for v in out:
                    k = (v.ent, v.tier)
                    if k not in seen:
                        seen.add(k)
                        res.append(adj(v, TIER_INFERRED, "type"))
                result = res
                break
        self._active.discard(key)
        self._attr_types[key] = result
        return result

    def _attr_binding_vals(self, ab, sc: Scope, mod, cid) -> list:
        if ab.kind == "ann":
            return self.ann_types(ab.ann, mod, cid)
        saved, self._emit = self._emit, []
        try:
            return self.eval_value(ab.shape, sc)
        finally:
            self._emit = saved

    # ------------------------------------------------------ value evaluation
    def eval_value(self, shape: Shape, sc: Scope, write_last: bool = False, depth: int = 0) -> list:
        if depth > 8:
            return [UNK]
        k = shape.kind
        if k == "name":
            vals = self.lookup_name(shape.base, sc)
            if not vals:
                return []
        elif k == "call":
            vals = self.call_result(shape.recv, sc, depth + 1)
        elif k == "coll":
            ents = []
            for e in shape.elems:
                for v in self.eval_value(e, sc, depth=depth + 1):
                    if v.ent[0] in ("cls", "fn", "inst"):
                        ents.append(v.ent)
            vals = [V(("coll", tuple(ents)), TIER_INFERRED, "table")]
        elif k == "index":
            vals = []
            for v in self.eval_value(shape.inner, sc, depth=depth + 1):
                vals += self.elements_of(v, index=True)
            vals = vals or [UNK]
        elif k == "super":
            cid = self.class_of_func(sc.func)
            vals = [V(("super", cid))] if cid else [UNK]
        elif k == "literal":
            vals = [V(("ext", "literal"))]
        else:
            vals = [UNK]
        n = len(shape.attrs)
        for i, attr in enumerate(shape.attrs):
            nxt = []
            for v in vals:
                nxt += self.step_attr(v, attr, sc, write=write_last and i == n - 1)
            vals = self._dedupe(nxt)
            if not vals:
                vals = [UNK]
        return vals

    @staticmethod
    def _dedupe(vals: list) -> list:
        seen, out = set(), []
        for v in vals:
            if v not in seen:
                seen.add(v)
                out.append(v)
        return out

    def call_result(self, cs: CallSite, sc: Scope, depth: int = 0) -> list:
        callee = self.eval_value(cs.shape, sc, depth=depth)
        out = []
        for v in callee:
            k = v.ent[0]
            if k == "cls":
                out.append(V(("inst", v.ent[1]), v.tier, v.via))
            elif k == "fn":
                f = self.funcs[v.ent[1]]
                if f.is_contextmanager:
                    ts = self.return_types(f, as_cm=True)
                else:
                    ts = self.return_types(f)
                out += [adj(t, v.tier, v.via) for t in ts] or [UNK]
            elif k == "inst":
                hit = self.find_member(self.mro(v.ent[1]), "__call__")
                if hit and hit[0] == "fn":
                    f = self.pick_func(hit[2])
                    out += [adj(t, v.tier) for t in self.return_types(f)] or [UNK]
                else:
                    out.append(UNK)
            elif k == "collfn":
                if v.ent[1] in ("get", "pop", "setdefault"):
                    out += [V(e, TIER_INFERRED, "table") for e in v.ent[2]] or [UNK]
                else:
                    out.append(V(("coll", v.ent[2]), v.tier, v.via))
            elif k == "mapfn":
                op, kc, vc = v.ent[1], v.ent[2], v.ent[3]
                if op == "items":
                    out.append(V(("pairs", kc, vc), v.tier, v.via))
                elif op == "values":
                    out.append(V(("seq", vc), v.tier, v.via) if vc else UNK)
                elif op == "keys":
                    out.append(V(("seq", kc), v.tier, v.via) if kc else UNK)
                else:
                    out += [V(("inst", c), TIER_INFERRED, "elem") for c in vc] or [UNK]
            elif k == "ext":
                nm = v.ent[1] or ""
                if nm in ("pytest.raises", "pytest.warns") and cs.arg_names:
                    cids = tuple(sorted({a.ent[1] for sh in cs.arg_names[:1]
                                         for a in self.eval_value(sh, sc, depth=depth) if a.ent[0] == "cls"}))
                    out.append(V(("excinfo", cids), TIER_INFERRED, "type") if cids else V(("ext", None), v.tier))
                elif nm.startswith("builtins.") and nm[9:] in SEQ_BUILTINS and cs.arg_names:
                    seqs = [t for t in self.eval_value(cs.arg_names[0], sc, depth=depth) if t.ent[0] == "seq"]
                    out += seqs or [V(("ext", None), v.tier)]
                else:
                    out.append(V(("ext", None), v.tier))
            elif k in ("miss", "opaque"):
                out.append(V(("opaque",)))
            else:
                out.append(UNK)
        return self._dedupe(out) or [UNK]

    def step_attr(self, v: V, attr: str, sc: Scope, write: bool = False) -> list:
        k = v.ent[0]
        if k == "mod":
            m = self.mod_by_name[v.ent[1]]
            sym = self.mod_symbol(m, attr, 0)
            if sym is not None:
                if sym[0] == "var":
                    return [adj(x, v.tier) for x in (self._sym_to_vals(sym, sc))]
                return [V(sym, v.tier, v.via)]
            sub = v.ent[1] + "." + attr
            if sub in self.mod_by_name:
                return [V(("mod", sub), v.tier)]
            if self.has_unresolved_star(m):
                return [V(("ext", f"{v.ent[1]}.{attr}"))]
            return [V(("opaque",))]
        if k == "ext":
            return [V(("ext", f"{v.ent[1]}.{attr}" if v.ent[1] else None), v.tier)]
        if k in ("cls", "inst", "super"):
            cid = v.ent[1]
            order = self.mro(cid)
            if k == "super":
                order = order[1:]
            hit = self.find_member(order, attr)
            if hit is None:
                if k in ("inst", "cls"):                          # instance / class attribute with a known type
                    ts = self.attr_types(cid, attr)
                    if ts is not None:
                        return [adj(t, v.tier) for t in ts] or [V(("opaque",))]
                if k == "cls" and self.is_enum(cid):
                    return [V(("inst", cid), TIER_INFERRED, "enum_member")]     # Color.RED is a Color
                if self.has_ext_base(cid):
                    return [V(("ext", None))]
                return [V(("miss", cid))]
            if hit[0] == "cls":
                return [V(("cls", hit[2]), v.tier, v.via)]
            owner, funcs = hit[1], hit[2]
            f = self.pick_func(funcs, want_setter=write)
            if write and f is None:
                f = self.pick_func(funcs)
            via, tier = v.via, v.tier
            if owner != cid or k == "super":
                tier = worse(tier, TIER_INFERRED) if not (k == "super" and owner in self.bases(cid)) else tier
                if owner != cid:
                    via = f"inherit:{owner}" if not (k == "super" and owner in self.bases(cid)) else via
            if f.is_property:
                self._emit.append(Target(f.id, tier, "property" if not via else f"property;{via}"))
                if write:
                    return [V(("opaque",))]
                ts = self.return_types(f)
                return [adj(t, tier, via) for t in ts] or [V(("opaque",))]
            return [V(("fn", f.id), tier, via, nodisp=(k == "super"))]
        if k == "excinfo":                                    # `with pytest.raises(E) as info: info.value`
            if attr == "value":
                return [V(("inst", c), TIER_INFERRED, "type") for c in v.ent[1]]
            return [V(("ext", None))]
        if k == "coll":
            if attr in ("get", "pop", "setdefault", "values", "copy"):
                return [V(("collfn", attr, v.ent[1]), v.tier, v.via)]
            return [V(("ext", None))]
        if k == "map":
            if attr in ("items", "values", "keys", "get", "pop", "setdefault"):
                return [V(("mapfn", attr, v.ent[1], v.ent[2]), v.tier, v.via)]
            return [V(("ext", None))]
        if k in ("fn", "seq", "pairs", "collfn", "mapfn"):
            return [V(("ext", None))]
        if k in ("cm",):
            return [UNK]
        if k in ("miss", "opaque"):
            return [V(("opaque",))]
        return [UNK]

    # ------------------------------------------------------ call resolution
    def dispatch_targets(self, f: FuncInfo, v: V) -> list:
        out = []
        if not f.class_id or f.name in ("__init__", "__new__", "__init_subclass__"):
            return out
        for d in self.descendants(f.class_id):
            fs = self.members.get(d, {}).get(f.name)
            if fs:
                g = self.pick_func(fs, want_setter=f.is_setter)
                if g is not None and g.id != f.id:
                    if not self._caller_is_test and self.mods[g.path].is_test:
                        continue            # production code never dispatches into test-local subclasses
                    out.append(Target(g.id, TIER_INFERRED, "dispatch"))
        return out

    def _fn_targets(self, v: V) -> list:
        f = self.funcs[v.ent[1]]
        ts = [Target(f.id, v.tier, v.via)]
        if not v.nodisp:
            ts += self.dispatch_targets(f, v)
        return ts

    def cat_of(self, shape: Shape, sc: Scope) -> str:
        if shape.kind == "super":
            return "self"
        if shape.kind in ("call", "literal", "other"):
            return {"call": "call_receiver", "literal": "literal", "other": "other"}[shape.kind]
        if not shape.attrs:
            return "bare_name"
        f = sc.func
        while f is not None:
            if shape.base in f.local_names:
                if shape.base == f.first_param and f.is_method:
                    return "self"
                return "local_var"
            f = self.funcs.get(f.parent_func) if f.parent_func else None
        sym = self.mod_symbol(sc.mod, shape.base, 0)
        if sym is None or sym[0] in ("mod", "ext"):
            return "module_attr"
        if sym[0] == "var":
            return "local_var"
        return "class_or_func_attr"

    def resolve_call(self, cs: CallSite, sc: Scope, owner_path: str) -> SiteRes:
        self._emit = []
        shape = cs.shape
        res = SiteRes("call", owner_path, cs.line, cs.col, cs.raw, cs.owner, self.cat_of(shape, sc), "unresolved",
                      guards=cs.guards, kwargs=cs.kwargs, npos=cs.npos, splat=cs.splat)
        vals = self.eval_value(shape, sc)
        self._classify(res, vals, shape, sc)
        return res

    def _classify(self, res: SiteRes, vals: list, shape: Shape, sc: Scope):
        targets: dict = {}

        def add(t: Target):
            old = targets.get(t.fid)
            if old is None or TIER_RANK[t.tier] < TIER_RANK[old.tier] or (
                    t.tier == old.tier and old.via == "dispatch" and t.via != "dispatch"):
                targets[t.fid] = t

        known = [v for v in vals if v.ent[0] != "unk"]
        use = known or vals
        saw_ext = saw_builtin = saw_noinit = saw_miss = saw_unk = saw_opaque = False
        for v in use:
            k = v.ent[0]
            if k == "fn":
                for t in self._fn_targets(v):
                    add(t)
            elif k == "cls":
                cid = v.ent[1]
                hit = self.find_member(self.mro(cid), "__init__")
                if hit and hit[0] == "fn":
                    f = self.pick_func(hit[2])
                    tier, via = v.tier, v.via
                    if hit[1] != cid:
                        tier, via = worse(tier, TIER_INFERRED), f"inherit:{hit[1]}"
                    add(Target(f.id, tier, via))
                elif self.has_ext_base(cid):
                    saw_ext = True
                else:
                    saw_noinit = True
            elif k == "inst":
                hit = self.find_member(self.mro(v.ent[1]), "__call__")
                if hit and hit[0] == "fn":
                    f = self.pick_func(hit[2])
                    add(Target(f.id, worse(v.tier, TIER_INFERRED), "type"))
                else:
                    saw_miss = True
            elif k in ("seq", "coll", "map", "pairs", "collfn", "mapfn", "excinfo"):
                saw_ext = True
            elif k == "ext":
                if v.ent[1] and v.ent[1].startswith("builtins.") and not shape.attrs:
                    saw_builtin = True
                else:
                    saw_ext = True
            elif k == "unk":
                saw_unk = True
            elif k == "miss":
                saw_miss = True
            elif k == "opaque":
                saw_opaque = True
            else:
                saw_opaque = True
        res.targets = list(targets.values())
        res.targets.extend(self._emit)   # property edges along the chain
        res.targets = self._merge_targets(res.targets)
        callish = [t for t in res.targets if not (t.via or "").startswith("property")]
        if callish:
            res.status = "resolved"
            return
        if saw_builtin:
            res.status = "builtin"
            return
        if saw_ext:
            res.status = "external"
            return
        if saw_noinit:
            res.status = "no_init"
            return
        if saw_unk and shape.attrs:
            self._unique_name(res, shape.attrs[-1], sc)
            return
        res.status = "unresolved"
        res.reason = ("attr_not_found" if saw_miss else "opaque_value" if saw_opaque
                      else "unknown_name" if not shape.attrs else "unknown_receiver")

    @staticmethod
    def _merge_targets(ts: list) -> list:
        best: dict = {}
        for t in ts:
            o = best.get(t.fid)
            if o is None or TIER_RANK[t.tier] < TIER_RANK[o.tier]:
                best[t.fid] = t
        return list(best.values())

    def _unique_name(self, res: SiteRes, name: str, sc: Scope):
        pool = self.methods_by_name.get(name, [])
        caller_is_test = sc.mod.is_test
        if not caller_is_test:
            pool = [f for f in pool if not self.mods[f.path].is_test]
        pool = [f for f in pool if not f.is_overload]
        ids = sorted({f.id for f in pool})
        guard = self.builtin_guard and name in BUILTIN_METHOD_NAMES
        props = [t for t in res.targets if (t.via or "").startswith("property")]
        if not ids:
            res.status = "unresolved"
            res.reason = "no_candidate"
            return
        if len(ids) == 1 and not guard:
            res.status = "resolved"
            res.targets = props + [Target(ids[0], TIER_INFERRED, "unique_name")]
            return
        res.status = "ambiguous"
        res.candidates = ids
        res.reason = "builtin_name_collision" if guard else "several_candidates"
        res.targets = props + [Target(i, TIER_AMBIGUOUS, "ambiguous") for i in ids]

    # --------------------------------------------------- other site kinds
    def resolve_access(self, ac, sc: Scope, owner_path: str) -> Optional[SiteRes]:
        self._emit = []
        self.eval_value(ac.shape, sc, write_last=ac.write)
        props = self._merge_targets(self._emit)
        if not props:
            return None
        return SiteRes("property", owner_path, ac.line, ac.col, ac.shape.raw, ac.owner,
                       "attr_access", "resolved", props)

    def _protocol_targets(self, v: V, names: tuple, first: bool, via: str) -> dict:
        targets: dict = {}
        if v.ent[0] != "inst":
            return targets
        for nm in names:
            hit = self.find_member(self.mro(v.ent[1]), nm)
            if hit and hit[0] == "fn":
                f = self.pick_func(hit[2])
                if f.is_property:
                    continue
                tier = worse(v.tier, TIER_INFERRED)
                vv = f"inherit:{hit[1]}" if hit[1] != v.ent[1] else via
                targets[f.id] = Target(f.id, tier, vv)
                for d in self.dispatch_targets(f, v):
                    targets.setdefault(d.fid, d)
                if first:
                    break
        return targets

    def resolve_implicit(self, im, sc: Scope, owner_path: str) -> Optional[SiteRes]:
        self._emit = []
        vals = self.eval_value(im.shape, sc)
        targets: dict = {}
        for v in vals:
            targets.update(self._protocol_targets(v, im.names, im.first, im.kind))
        if not targets:
            return None
        return SiteRes("implicit", owner_path, im.line, im.col, im.raw, im.owner, im.kind, "resolved",
                       self._merge_targets(list(targets.values())))

    BUILTIN_PROTO = {
        "len": (("__len__",), True), "repr": (("__repr__",), True), "str": (("__str__", "__repr__"), True),
        "print": (("__str__", "__repr__"), True), "format": (("__format__", "__str__", "__repr__"), True),
        "iter": (("__iter__",), False), "next": (("__next__",), False), "hash": (("__hash__",), True),
        "bool": (("__bool__", "__len__"), True), "bytes": (("__bytes__",), True),
        "list": (("__iter__", "__next__"), False), "tuple": (("__iter__", "__next__"), False),
        "set": (("__iter__", "__next__"), False), "frozenset": (("__iter__", "__next__"), False),
        "sorted": (("__iter__", "__next__"), False), "sum": (("__iter__", "__next__"), False),
        "min": (("__iter__", "__next__"), False), "max": (("__iter__", "__next__"), False),
        "any": (("__iter__", "__next__"), False), "all": (("__iter__", "__next__"), False),
        "enumerate": (("__iter__", "__next__"), False), "zip": (("__iter__", "__next__"), False),
        "reversed": (("__reversed__", "__iter__"), True), "dict": (("__iter__", "keys"), False),
        "map": (("__iter__", "__next__"), False), "filter": (("__iter__", "__next__"), False),
        "isinstance": ((), True),
    }

    def resolve_builtin_protocol(self, cs: CallSite, sc: Scope, owner_path: str) -> Optional[SiteRes]:
        proto = self.BUILTIN_PROTO.get(cs.shape.base)
        if not proto or not proto[0]:
            return None
        targets: dict = {}
        elem_names = {"sorted": ("__lt__",), "min": ("__lt__",), "max": ("__lt__",)}.get(cs.shape.base)
        for sh in cs.arg_names:
            for v in self.eval_value(sh, sc):
                targets.update(self._protocol_targets(v, proto[0], proto[1], "builtin:" + cs.shape.base))
                if elem_names and v.ent[0] in ("seq", "map"):
                    for e in self.elements_of(v):
                        targets.update(self._protocol_targets(e, elem_names, True, "builtin:" + cs.shape.base))
                if elem_names and v.ent[0] == "pairs":
                    for c in v.ent[1]:
                        targets.update(self._protocol_targets(V(("inst", c), TIER_INFERRED, "elem"), elem_names,
                                                              True, "builtin:" + cs.shape.base))
        if not targets:
            return None
        return SiteRes("implicit", owner_path, cs.line, cs.col, cs.raw, cs.owner,
                       "builtin_protocol", "resolved", self._merge_targets(list(targets.values())))

    def resolve_escape(self, cs: CallSite, sc: Scope, owner_path: str) -> Optional[SiteRes]:
        """Instances handed to *external* code may have their dunders invoked there
        (pickle -> __getstate__, cookiejar -> methods, logging -> __repr__, ...): AMBIGUOUS."""
        targets: dict = {}
        for sh in cs.arg_names:
            inline = sh.kind == "call" and not sh.attrs
            for v in self.eval_value(sh, sc):
                if v.ent[0] != "inst":
                    continue
                cid = v.ent[1]
                for name, fs in self.members.get(cid, {}).items():
                    if name in ("__init__", "__new__"):
                        continue
                    kc = self.classes[cid]
                    # inline instance, subclass of an external class, or a private/nested adapter class
                    plug = inline or self.has_ext_base(cid) or kc.is_nested or kc.name.startswith("_")
                    if not plug and not (name.startswith("__") and name.endswith("__")):
                        continue
                    f = self.pick_func(fs)
                    if f is not None and not f.is_property:
                        targets[f.id] = Target(f.id, TIER_AMBIGUOUS, "escape")
        if not targets:
            return None
        return SiteRes("implicit", owner_path, cs.line, cs.col, cs.raw, cs.owner, "escape",
                       "ambiguous", list(targets.values()), [])

    def resolve_refs(self, cs: CallSite, sc: Scope, owner_path: str) -> Optional[SiteRes]:
        targets = {}
        for sh in cs.arg_names:
            vals = self.eval_value(sh, sc)
            for v in vals:
                if v.ent[0] == "fn":
                    f = self.funcs[v.ent[1]]
                    if f.is_property:
                        continue
                    targets[f.id] = Target(f.id, TIER_INFERRED, "ref")
        if not targets:
            return None
        return SiteRes("ref", owner_path, cs.line, cs.col, cs.raw, cs.owner, "arg_ref", "resolved",
                       list(targets.values()))

    # -------------------------------------------------------------- driver
    def resolve_dynamic(self, cs: CallSite, sc: Scope, owner_path: str) -> Optional[SiteRes]:
        """getattr(obj, "name") and getattr(obj, "prefix" + x): edges to the methods they can name.

        A literal name is INFERRED (the name is in the source; the receiver's class has it). A known
        prefix reaches every method of the receiver's class that starts with it: AMBIGUOUS, one edge
        per candidate. An unknown name adds nothing.
        """
        receiver, (kind, text) = cs.dyn
        if kind == "unknown":
            return None
        targets: dict = {}
        for v in self.eval_value(receiver, sc):
            if v.ent[0] not in ("inst", "cls"):
                continue
            order = self.mro(v.ent[1])
            if kind == "literal":
                names = [text]
            else:
                names = sorted({n for c in order for n in self.members.get(c, {}) if n.startswith(text)})
            for name in names:
                hit = self.find_member(order, name)
                if not hit or hit[0] != "fn":
                    continue
                f = self.pick_func(hit[2])
                if f is None or f.is_property:
                    continue
                tier = TIER_INFERRED if kind == "literal" else TIER_AMBIGUOUS
                via = "getattr" if kind == "literal" else "getattr_prefix"
                targets.setdefault(f.id, Target(f.id, tier, via))
        if not targets:
            return None
        ambiguous = any(t.tier == TIER_AMBIGUOUS for t in targets.values())
        return SiteRes("dynamic", owner_path, cs.line, cs.col, cs.raw, cs.owner, "getattr",
                       "ambiguous" if ambiguous else "resolved", list(targets.values()),
                       sorted(targets) if ambiguous else [],
                       reason=f"{kind}:{text}")   # the pattern, for the incremental update

    def resolve_module(self, mod: ModuleInfo) -> list:
        """Resolve every site owned by `mod` (module level and all its functions)."""
        out = []
        self._caller_is_test = mod.is_test
        scopes = [(mod, Scope(mod, None))] + [(f, Scope(mod, f)) for f in mod.funcs]
        for owner, sc in scopes:
            for cs in owner.calls:
                site = self.resolve_call(cs, sc, mod.path)
                out.append(site)
                if cs.dyn:
                    dyn = self.resolve_dynamic(cs, sc, mod.path)
                    if dyn is not None:
                        out.append(dyn)
                if cs.arg_names:
                    if self.enable_ref_edges:
                        r = self.resolve_refs(cs, sc, mod.path)
                        if r:
                            out.append(r)
                    if site.status == "builtin":
                        r = self.resolve_builtin_protocol(cs, sc, mod.path)
                        if r:
                            out.append(r)
                    elif site.status == "external":
                        r = self.resolve_escape(cs, sc, mod.path)
                        if r:
                            out.append(r)
            for ac in owner.accesses:
                r = self.resolve_access(ac, sc, mod.path)
                if r:
                    out.append(r)
            for im in owner.implicits:
                r = self.resolve_implicit(im, sc, mod.path)
                if r:
                    out.append(r)
        return out
