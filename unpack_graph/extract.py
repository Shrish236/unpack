"""PASS 1: Extraction of ModuleInfo from source bytes using AST and Tree-sitter."""

from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path
from typing import Any

from .model import (
    AttrAccess,
    AttrBinding,
    Binding,
    CallSite,
    ClassInfo,
    FuncInfo,
    Implicit,
    ImportRec,
    ModuleInfo,
    Shape,
)

PROPERTY_DECOS = {"property", "cached_property"}
FIXTURE_DECOS = {"fixture", "pytest.fixture"}
ABSTRACT_DECOS = {"abstractmethod"}


def hash_str(text: str) -> str:
    """Compute 16-hex short hash."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def normalize_logic_tokens(code_text: str) -> str:
    """Strip docstrings, comments and whitespace for logic_hash."""
    try:
        tree = ast.parse(code_text)
        # Strip docstring if present
        if (
            tree.body
            and isinstance(tree.body[0], (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and tree.body[0].body
            and isinstance(tree.body[0].body[0], ast.Expr)
            and isinstance(tree.body[0].body[0].value, ast.Constant)
            and isinstance(tree.body[0].body[0].value.value, str)
        ):
            tree.body[0].body.pop(0)
        # Convert stripped ast back to unparsed normalized text
        return ast.unparse(tree)
    except Exception:
        # Fallback to simple regex comment and whitespace stripper
        no_comments = re.sub(r"#.*$", "", code_text, flags=re.MULTILINE)
        return "".join(no_comments.split())


def module_name_for(path: str, all_files: set[str] | None = None) -> tuple[str, str]:
    """Compute (dotted_module_name, package) from path and __init__.py ancestry."""
    p = Path(path)
    parts = list(p.parts)
    if parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    if parts[-1] == "__init__":
        parts.pop()
        pkg = ".".join(parts)
        return (pkg, pkg)

    # Check ancestry for src/ layout or packages
    pkg_parts = parts[:-1]
    if pkg_parts and pkg_parts[0] in ("src", "lib"):
        pkg_parts = pkg_parts[1:]
        parts = parts[1:]

    mod_name = ".".join(parts)
    pkg_name = ".".join(pkg_parts)
    return (mod_name, pkg_name)


def is_test_path(path: str) -> bool:
    """Check if file path belongs to a test suite."""
    p = Path(path).as_posix().lower()
    return (
        "/tests/" in p
        or "/test/" in p
        or p.startswith("tests/")
        or p.startswith("test/")
        or p.endswith("_test.py")
        or Path(path).name.startswith("test_")
        or Path(path).name == "conftest.py"
    )


class ASTExtractor(ast.NodeVisitor):
    """Fallback & validation extractor built with Python stdlib ast."""

    def __init__(self, path: str, source_bytes: bytes, mod_name: str, package: str) -> None:
        self.path = path
        self.raw_text = source_bytes.decode("utf-8", errors="replace")
        self.lines = self.raw_text.splitlines()
        self.mod_name = mod_name
        self.package = package
        self.is_test_file = is_test_path(path)

        self.qualname_stack: list[str] = []
        self.class_stack: list[ClassInfo] = []
        self.func_stack: list[FuncInfo] = []

        self.funcs: list[FuncInfo] = []
        self.classes: list[ClassInfo] = []
        self.imports: list[ImportRec] = []
        self.module_calls: list[CallSite] = []
        self.module_bindings: list[Binding] = []
        self.all_exports: list[str] = []

        self.id_counters: dict[str, int] = {}

    def get_slice(self, start_line: int, end_line: int) -> str:
        s = max(0, start_line - 1)
        e = min(len(self.lines), end_line)
        return "\n".join(self.lines[s:e])

    def current_owner(self) -> str:
        if self.func_stack:
            return self.func_stack[-1].id
        return self.path

    def parse_shape(self, node: ast.AST | None) -> Shape:
        if node is None:
            return Shape(kind="other")
        if isinstance(node, ast.Name):
            return Shape(kind="name", base=node.id)
        if isinstance(node, ast.Attribute):
            base_shape = self.parse_shape(node.value)
            attrs = list(base_shape.attrs) + [node.attr]
            return Shape(kind="attr", base=base_shape.base, attrs=attrs, recv=base_shape.recv)
        if isinstance(node, ast.Call):
            callee_shape = self.parse_shape(node.func)
            cs = CallSite(
                line=getattr(node, "lineno", 0),
                col=getattr(node, "col_offset", 0),
                raw=ast.unparse(node),
                callee=callee_shape,
                owner=self.current_owner(),
            )
            return Shape(kind="call", recv=cs)
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            elems = [ast.unparse(el) for el in node.elts]
            return Shape(kind="coll", elems=elems)
        if isinstance(node, ast.Constant):
            return Shape(kind="literal", base=str(node.value))
        return Shape(kind="other", base=ast.unparse(node))

    def visit_Import(self, node: ast.Import) -> None:
        rec = ImportRec(
            kind="import",
            module="",
            level=0,
            names=[(alias.name, alias.asname) for alias in node.names],
            owner=self.current_owner(),
        )
        self.imports.append(rec)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        mod = node.module or ""
        star = any(alias.name == "*" for alias in node.names)
        names = [(alias.name, alias.asname) for alias in node.names if alias.name != "*"]
        rec = ImportRec(
            kind="from",
            module=mod,
            level=node.level or 0,
            names=names,
            star=star,
            owner=self.current_owner(),
        )
        self.imports.append(rec)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        name = node.name
        self.qualname_stack.append(name)
        qualname = ".".join(self.qualname_stack)
        cid = f"{self.path}::{qualname}"

        bases = [ast.unparse(b) for b in node.bases]
        decos = [ast.unparse(d) for d in node.decorator_list]
        doc = ast.get_docstring(node)
        start = node.lineno
        end = getattr(node, "end_lineno", start)
        body_text = self.get_slice(start, end)

        cls_info = ClassInfo(
            id=cid,
            name=name,
            qualname=qualname,
            path=self.path,
            start=start,
            end=end,
            bases_raw=bases,
            decorators=decos,
            doc=doc,
            doc_hash=hash_str(doc or ""),
            logic_hash=hash_str(normalize_logic_tokens(body_text)),
        )
        self.classes.append(cls_info)
        self.class_stack.append(cls_info)

        self.generic_visit(node)

        self.class_stack.pop()
        self.qualname_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        name = node.name
        is_async = isinstance(node, ast.AsyncFunctionDef)
        is_method = len(self.class_stack) > 0

        self.qualname_stack.append(name)
        qualname = ".".join(self.qualname_stack)
        base_id = f"{self.path}::{qualname}"

        decos = [ast.unparse(d) for d in node.decorator_list]
        is_prop = any(d in PROPERTY_DECOS or d.endswith(".setter") for d in decos)
        is_setter = any(d.endswith(".setter") for d in decos)

        # Disambiguation suffix
        suffix = ""
        if is_setter:
            suffix = "#setter"
        else:
            count = self.id_counters.get(base_id, 0)
            if count > 0:
                suffix = f"#{count + 1}"
            self.id_counters[base_id] = count + 1

        fid = f"{base_id}{suffix}"

        start = node.lineno
        end = getattr(node, "end_lineno", start)
        body_text = self.get_slice(start, end)

        # Detect tests and fixtures
        is_test = False
        if self.is_test_file:
            if name.startswith("test_") or (is_method and name.startswith("test")):
                is_test = True
        is_fixture = any(any(f in d for f in FIXTURE_DECOS) for d in decos)
        is_abstract = any(d in ABSTRACT_DECOS for d in decos)

        # Params & signature
        params = []
        for arg in node.args.args:
            params.append({
                "name": arg.arg,
                "ann": ast.unparse(arg.annotation) if arg.annotation else None,
            })
        returns = ast.unparse(node.returns) if node.returns else None

        sig_tokens = f"{'async ' if is_async else ''}def {name}({', '.join(p['name'] for p in params)})"
        if returns:
            sig_tokens += f" -> {returns}"

        doc = ast.get_docstring(node)

        f_info = FuncInfo(
            id=fid,
            qualname=qualname,
            name=name,
            path=self.path,
            start=start,
            end=end,
            is_async=is_async,
            is_method=is_method,
            is_test=is_test,
            is_fixture=is_fixture,
            is_abstract=is_abstract,
            is_property=is_prop,
            is_setter=is_setter,
            decorators=decos,
            signature=sig_tokens,
            doc=doc,
            body_hash=hash_str(body_text),
            logic_hash=hash_str(normalize_logic_tokens(body_text)),
            signature_hash=hash_str(sig_tokens),
            params=params,
            returns=returns,
        )
        self.funcs.append(f_info)
        self.func_stack.append(f_info)

        self.generic_visit(node)

        self.func_stack.pop()
        self.qualname_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)

    def visit_Call(self, node: ast.Call) -> None:
        callee_shape = self.parse_shape(node.func)
        kwargs = [kw.arg for kw in node.keywords if kw.arg]
        npos = len(node.args)
        splat = any(kw.arg is None for kw in node.keywords) or any(isinstance(a, ast.Starred) for a in node.args)

        cs = CallSite(
            line=node.lineno,
            col=node.col_offset,
            raw=ast.unparse(node),
            callee=callee_shape,
            owner=self.current_owner(),
            kwargs=kwargs,
            npos=npos,
            splat=splat,
        )

        if self.func_stack:
            self.func_stack[-1].calls.append(cs)
        else:
            self.module_calls.append(cs)

        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        # Track bindings like x = Cls(...) or self.attr = ...
        val_shape = self.parse_shape(node.value)
        for target in node.targets:
            if isinstance(target, ast.Name):
                b = Binding(name=target.id, kind="val", val=val_shape, line=node.lineno)
                if self.func_stack:
                    self.func_stack[-1].bindings.append(b)
                else:
                    self.module_bindings.append(b)
            elif isinstance(target, ast.Attribute):
                raw_t = ast.unparse(target)
                ab = AttrBinding(target=raw_t, val=val_shape, line=node.lineno)
                if self.func_stack:
                    self.func_stack[-1].attr_bindings.append(ab)
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            dunder = "__enter__"
            imp = Implicit(line=node.lineno, kind="with", dunder=dunder, owner=self.current_owner())
            if self.func_stack:
                self.func_stack[-1].implicits.append(imp)
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        imp = Implicit(line=node.lineno, kind="for", dunder="__iter__", owner=self.current_owner())
        if self.func_stack:
            self.func_stack[-1].implicits.append(imp)
        self.generic_visit(node)


def extract_file(path: str, data: bytes, module_name: str | None = None, package: str | None = None) -> ModuleInfo:
    """Extract ModuleInfo from file path and content bytes."""
    if module_name is None or package is None:
        mod_name, pkg = module_name_for(path)
    else:
        mod_name, pkg = module_name, package

    is_test = is_test_path(path)
    raw_text = data.decode("utf-8", errors="replace")
    nlines = len(raw_text.splitlines())

    extractor = ASTExtractor(path, data, mod_name, pkg)
    try:
        tree = ast.parse(data, filename=path)
        extractor.visit(tree)
        partial = False
    except SyntaxError:
        partial = True

    return ModuleInfo(
        id=path,
        path=path,
        name=mod_name,
        package=pkg,
        is_test=is_test,
        partial=partial,
        imports=extractor.imports,
        defs=extractor.funcs,
        classes=extractor.classes,
        calls=extractor.module_calls,
        bindings=extractor.module_bindings,
        all_exports=extractor.all_exports,
        logic_hash=hash_str(normalize_logic_tokens(raw_text)),
        nlines=nlines,
    )
