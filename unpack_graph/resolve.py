"""PASS 2: Whole-repository symbol, import, type and call resolution."""

from __future__ import annotations

from typing import Any

from .model import (
    ClassInfo,
    FuncInfo,
    ModuleInfo,
    SiteRes,
    Tier,
)

BUILTIN_NAMES = {
    "len", "str", "repr", "int", "float", "bool", "list", "dict", "set", "tuple",
    "isinstance", "issubclass", "getattr", "setattr", "hasattr", "print", "min", "max",
    "sorted", "range", "enumerate", "zip", "open", "any", "all", "sum"
}

BUILTIN_METHOD_NAMES = {
    "get", "keys", "values", "items", "append", "extend", "pop", "insert",
    "remove", "clear", "index", "count", "sort", "reverse", "copy", "update",
    "split", "join", "strip", "startswith", "endswith", "replace", "lower", "upper",
    "read", "write", "close", "flush"
}


class Resolver:
    """Pass 2 symbol resolver across all extracted modules in the repo."""

    def __init__(self, mods: dict[str, ModuleInfo], opts: dict[str, Any] | None = None) -> None:
        self.mods = mods
        self.opts = opts or {}
        self.mod_by_name: dict[str, ModuleInfo] = {m.name: m for m in mods.values()}

        self.funcs: dict[str, FuncInfo] = {}
        self.classes: dict[str, ClassInfo] = {}
        self.members: dict[str, dict[str, list[str]]] = {}
        self.methods_by_name: dict[str, list[str]] = {}

        self._build_indices()

    def _build_indices(self) -> None:
        for mod in self.mods.values():
            for c in mod.classes:
                self.classes[c.id] = c
                self.members[c.id] = {}

            for f in mod.defs:
                self.funcs[f.id] = f
                # Index methods under classes
                if f.is_method:
                    parent_cid = f.id.rsplit(".", 1)[0].replace("#setter", "")
                    if parent_cid in self.members:
                        self.members[parent_cid].setdefault(f.name, []).append(f.id)
                    self.methods_by_name.setdefault(f.name, []).append(f.id)

    def resolve_all(self) -> list[SiteRes]:
        """Resolve all call sites and implicit sites across the codebase."""
        results: list[SiteRes] = []
        for mod in self.mods.values():
            for f in mod.defs:
                for cs in f.calls:
                    res = self._resolve_call(cs, f)
                    results.append(res)
                for imp in f.implicits:
                    res = self._resolve_implicit(imp, f)
                    if res:
                        results.append(res)
        return results

    def _resolve_call(self, cs: Any, owner_fn: FuncInfo) -> SiteRes:
        shape = cs.callee
        raw = cs.raw
        owner_id = owner_fn.id

        # 1. Bare name call: foo()
        if shape.kind == "name":
            name = shape.base
            if name in BUILTIN_NAMES:
                return SiteRes(kind="call", status="builtin", raw=raw, line=cs.line, owner=owner_id)

            # Check if it resolves to a function in the same module
            mod = self.mods.get(owner_fn.path)
            if mod:
                for f in mod.defs:
                    if f.name == name and not f.is_method:
                        return SiteRes(
                            kind="call",
                            status="resolved",
                            targets=[(f.id, "EXTRACTED", "local")],
                            raw=raw,
                            line=cs.line,
                            owner=owner_id,
                            kwargs=cs.kwargs,
                            npos=cs.npos,
                            splat=cs.splat,
                            guards=cs.guards,
                        )
                # Check imported functions
                for imp in mod.imports:
                    for imp_name, alias in imp.names:
                        target_name = alias or imp_name
                        if target_name == name:
                            target_mod = self.mod_by_name.get(imp.module)
                            if target_mod:
                                for f in target_mod.defs:
                                    if f.name == imp_name:
                                        return SiteRes(
                                            kind="call",
                                            status="resolved",
                                            targets=[(f.id, "EXTRACTED", "import")],
                                            raw=raw,
                                            line=cs.line,
                                            owner=owner_id,
                                            kwargs=cs.kwargs,
                                            npos=cs.npos,
                                            splat=cs.splat,
                                            guards=cs.guards,
                                        )

            # Check if it's a class instantiation: Cls()
            for c in self.classes.values():
                if c.name == name:
                    init_id = f"{c.id}.__init__"
                    if init_id in self.funcs:
                        return SiteRes(
                            kind="call",
                            status="resolved",
                            targets=[(init_id, "EXTRACTED", "constructor")],
                            raw=raw,
                            line=cs.line,
                            owner=owner_id,
                            kwargs=cs.kwargs,
                            npos=cs.npos,
                            splat=cs.splat,
                            guards=cs.guards,
                        )
                    return SiteRes(kind="call", status="no_init", raw=raw, line=cs.line, owner=owner_id)

            return SiteRes(kind="call", status="unresolved", reason="unknown_name", raw=raw, line=cs.line, owner=owner_id)

        # 2. Attribute call: self.method() or obj.method()
        if shape.kind == "attr":
            method_name = shape.attrs[-1] if shape.attrs else ""
            base = shape.base

            # Method on self/cls
            if base in ("self", "cls") and owner_fn.is_method:
                class_id = owner_fn.id.rsplit(".", 1)[0].replace("#setter", "")
                if class_id in self.members and method_name in self.members[class_id]:
                    target_id = self.members[class_id][method_name][0]
                    targets = [(target_id, "EXTRACTED", "self")]

                    # Check abstract dispatch overrides
                    targets.extend(self._find_overrides(class_id, method_name))

                    return SiteRes(
                        kind="call",
                        status="resolved",
                        targets=targets,
                        raw=raw,
                        line=cs.line,
                        owner=owner_id,
                        kwargs=cs.kwargs,
                        npos=cs.npos,
                        splat=cs.splat,
                        guards=cs.guards,
                    )

            # Unique method name fallback across repo
            candidates = self.methods_by_name.get(method_name, [])
            if candidates:
                if len(candidates) == 1 and method_name not in BUILTIN_METHOD_NAMES:
                    return SiteRes(
                        kind="call",
                        status="resolved",
                        targets=[(candidates[0], "INFERRED", "unique_name")],
                        candidates=candidates,
                        raw=raw,
                        line=cs.line,
                        owner=owner_id,
                        kwargs=cs.kwargs,
                        npos=cs.npos,
                        splat=cs.splat,
                        guards=cs.guards,
                    )
                else:
                    return SiteRes(
                        kind="call",
                        status="ambiguous",
                        targets=[(c, "AMBIGUOUS", "method_name") for c in candidates],
                        candidates=candidates,
                        raw=raw,
                        line=cs.line,
                        owner=owner_id,
                        kwargs=cs.kwargs,
                        npos=cs.npos,
                        splat=cs.splat,
                        guards=cs.guards,
                    )

            if method_name in BUILTIN_METHOD_NAMES:
                return SiteRes(kind="call", status="builtin", raw=raw, line=cs.line, owner=owner_id)

            return SiteRes(kind="call", status="unresolved", reason="no_candidate", raw=raw, line=cs.line, owner=owner_id)

        return SiteRes(kind="call", status="unresolved", reason="complex_shape", raw=raw, line=cs.line, owner=owner_id)

    def _resolve_implicit(self, imp: Any, owner_fn: FuncInfo) -> SiteRes | None:
        """Resolve implicit protocol sites to dunder methods."""
        dunder = imp.dunder
        candidates = self.methods_by_name.get(dunder, [])
        if not candidates:
            return None
        targets = [(c, "INFERRED", f"implicit:{imp.kind}") for c in candidates[:5]]
        return SiteRes(
            kind="implicit",
            status="resolved" if len(targets) == 1 else "ambiguous",
            targets=targets,
            raw=dunder,
            line=imp.line,
            owner=owner_fn.id,
        )

    def _find_overrides(self, class_id: str, method_name: str) -> list[tuple[str, Tier, str]]:
        """Find overriding methods in subclasses for abstract/base dispatch."""
        overrides: list[tuple[str, Tier, str]] = []
        for other_cid, m_dict in self.members.items():
            if other_cid != class_id and method_name in m_dict:
                # If other_cid inherits from class_id
                cls_info = self.classes.get(other_cid)
                parent_info = self.classes.get(class_id)
                if cls_info and parent_info and parent_info.name in cls_info.bases_raw:
                    for fid in m_dict[method_name]:
                        overrides.append((fid, "INFERRED", "dispatch"))
        return overrides
