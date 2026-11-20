"""Pass 1: per-file extraction with tree-sitter.

A single recursive walk with a qualname stack.  Nothing here looks at other files;
everything that needs cross-file knowledge is deferred to resolve.py.
"""
from __future__ import annotations

import ast
import hashlib
import sys
from dataclasses import dataclass
from typing import Optional

import tree_sitter_python as _tsp
from tree_sitter import Language, Parser

from .model import (AttrAccess, AttrBinding, Binding, CallSite, ClassInfo, FuncInfo,
                    Implicit, ImportRec, ModuleInfo, Shape)

_LANG = Language(_tsp.language())
sys.setrecursionlimit(max(sys.getrecursionlimit(), 20000))

LITERAL_TYPES = {
    "string", "concatenated_string", "integer", "float", "true", "false", "none",
    "list", "dictionary", "set", "tuple", "list_comprehension", "dictionary_comprehension",
    "set_comprehension", "generator_expression", "ellipsis",
}
PROPERTY_DECOS = {"property", "cached_property", "functools.cached_property", "abc.abstractproperty",
                  "abstractproperty"}
ABSTRACT_DECOS = {"abstractmethod", "abc.abstractmethod", "abc.abstractproperty", "abstractproperty"}
CM_DECOS = {"contextmanager", "contextlib.contextmanager", "asynccontextmanager",
            "contextlib.asynccontextmanager"}
FIXTURE_DECOS = {"pytest.fixture", "fixture", "pytest_asyncio.fixture", "pytest.yield_fixture"}
OVERLOAD_DECOS = {"overload", "typing.overload", "typing_extensions.overload"}


def _h(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8", "replace")).hexdigest()[:16]


def is_test_path(path: str) -> bool:
    parts = path.split("/")
    name = parts[-1]
    return ("tests" in parts[:-1] or "test" in parts[:-1] or name.startswith("test_")
            or name.endswith("_test.py") or name == "conftest.py")


@dataclass
class Ctx:
    scope: object                  # ModuleInfo | FuncInfo (collector of calls/bindings)
    scope_id: str
    qual: str                      # qualname of the current container ('' for module)
    kind: str                      # module | class | func
    cls: Optional[ClassInfo]
    func: Optional[FuncInfo]       # innermost enclosing function
    tc: bool = False
    in_try: bool = False


class Walker:
    def __init__(self, path: str, data: bytes, mod: ModuleInfo):
        self.path = path
        self.data = data
        self.mod = mod
        self.cs_memo: dict[int, CallSite] = {}
        self.seen_ids: dict[str, int] = {}
        self.write_flag = False
        self.sub_mode = "get"
        self.is_test_file = mod.is_test

    # ------------------------------------------------------------- helpers
    def txt(self, node) -> str:
        return self.data[node.start_byte:node.end_byte].decode("utf-8", "replace")

    def end_line(self, node) -> int:
        """Last line of a def/class like `ast.end_lineno`: tree-sitter's blocks also swallow trailing
        indented comments, `ast` stops at the last token of the last statement.  Descend to the
        rightmost non-comment leaf."""
        n = node
        while True:
            kids = [c for c in n.children if c.type != "comment"]
            if not kids:
                return n.end_point[0] + 1
            n = kids[-1]

    def collapse(self, s: str, n: int = 160) -> str:
        s = " ".join(s.split())
        return s if len(s) <= n else s[: n - 1] + "…"

    def uid(self, base: str, extra_suffix: str = "") -> str:
        cand = base + extra_suffix
        n = self.seen_ids.get(cand, 0)
        self.seen_ids[cand] = n + 1
        if n == 0:
            return cand
        return f"{cand}#{n + 1}"

    def peel(self, node):
        """Strip attribute/paren/await wrappers down to the base expression node."""
        while True:
            t = node.type
            if t == "attribute":
                node = node.child_by_field_name("object")
            elif t == "parenthesized_expression":
                kids = [c for c in node.children if c.is_named]
                if len(kids) != 1:
                    return node
                node = kids[0]
            elif t == "await":
                kids = [c for c in node.children if c.is_named]
                if not kids:
                    return node
                node = kids[-1]
            else:
                return node

    def shape(self, node, ctx: Ctx) -> Shape:
        attrs = []
        cur = node
        while True:
            t = cur.type
            if t == "attribute":
                attrs.append(self.txt(cur.child_by_field_name("attribute")))
                cur = cur.child_by_field_name("object")
            elif t == "parenthesized_expression":
                kids = [c for c in cur.children if c.is_named]
                if len(kids) != 1:
                    break
                cur = kids[0]
            elif t == "await":
                kids = [c for c in cur.children if c.is_named]
                if not kids:
                    break
                cur = kids[-1]
            else:
                break
        attrs.reverse()
        t = cur.type
        raw = self.collapse(self.txt(node), 120)
        if t == "identifier":
            return Shape("name", self.txt(cur), tuple(attrs), None, raw)
        if t == "call":
            fn = cur.child_by_field_name("function")
            args = cur.child_by_field_name("arguments")
            if fn is not None and fn.type == "identifier" and self.txt(fn) == "super" and (
                    args is None or args.named_child_count == 0):
                return Shape("super", "", tuple(attrs), None, raw)
            recv = self.callsite(cur, ctx)
            return Shape("call", "", tuple(attrs), recv, raw)
        if t in LITERAL_TYPES:
            return Shape("literal", "", tuple(attrs), None, raw)
        return Shape("other", "", tuple(attrs), None, raw)

    # ---- guards: parameters whose positive test encloses a call (`if p:`, `if p is not None:`)
    def positive_names(self, cond) -> list:
        if cond is None:
            return []
        t = cond.type
        if t == "identifier":
            return [self.txt(cond)]
        if t == "parenthesized_expression":
            kids = [c for c in cond.children if c.is_named]
            return self.positive_names(kids[0]) if len(kids) == 1 else []
        if t == "comparison_operator":
            toks = " ".join(self.txt(c) for c in cond.children if not c.is_named).split()
            ops = [c for c in cond.children if c.is_named]
            if len(ops) == 2 and ops[0].type == "identifier" and ops[1].type == "none" and \
                    toks in (["is", "not"], ["!="]):
                return [self.txt(ops[0])]
            return []
        if t == "boolean_operator":
            op = cond.child_by_field_name("operator")
            if op is not None and self.txt(op) == "and":
                return (self.positive_names(cond.child_by_field_name("left"))
                        + self.positive_names(cond.child_by_field_name("right")))
        return []

    def guards_of(self, node) -> tuple:
        names: list = []
        ch, p = node, node.parent
        while p is not None and p.type not in ("function_definition", "class_definition", "lambda", "module"):
            if p.type in ("if_statement", "elif_clause"):
                cons = p.child_by_field_name("consequence")
                if cons is not None and ch.id == cons.id:
                    names += self.positive_names(p.child_by_field_name("condition"))
            elif p.type == "boolean_operator":
                op = p.child_by_field_name("operator")
                right = p.child_by_field_name("right")
                if op is not None and self.txt(op) == "and" and right is not None and ch.id == right.id:
                    names += self.positive_names(p.child_by_field_name("left"))
            ch, p = p, p.parent
        return tuple(sorted(set(names)))

    def callsite(self, node, ctx: Ctx) -> CallSite:
        cs = self.cs_memo.get(node.id)
        if cs is not None:
            return cs
        fn = node.child_by_field_name("function")
        args = node.child_by_field_name("arguments")
        arg_shapes = []
        if args is not None and args.type == "argument_list":
            for a in args.named_children:
                v = a.child_by_field_name("value") if a.type == "keyword_argument" else a
                if v is None:
                    continue
                if v.type in ("identifier", "attribute"):
                    sh = self.shape(v, ctx)
                    if sh.kind == "name":
                        arg_shapes.append(sh)
                elif v.type == "call":
                    arg_shapes.append(Shape("call", "", (), self.callsite(v, ctx), self.collapse(self.txt(v), 120)))
        parent = node.parent
        kwargs, npos, splat = [], 0, False
        if args is not None and args.type == "argument_list":
            for a in args.named_children:
                if a.type == "keyword_argument":
                    kwargs.append(self.txt(a.child_by_field_name("name")))
                elif a.type in ("list_splat", "dictionary_splat"):
                    splat = True
                elif a.type != "comment":
                    npos += 1
        elif args is not None:
            npos = 1                     # generator-expression argument
        cs = CallSite(
            line=node.start_point[0] + 1, col=node.start_point[1],
            end_line=node.end_point[0] + 1, raw=self.collapse(self.txt(node)),
            shape=self.shape(fn, ctx) if fn is not None else Shape("other"),
            owner=ctx.scope_id, arg_names=tuple(arg_shapes),
            is_await=parent is not None and parent.type == "await",
            kwargs=tuple(kwargs), npos=npos, splat=splat, guards=self.guards_of(node),
            dyn=self.dynamic_getattr(fn, args, ctx),
        )
        self.cs_memo[node.id] = cs
        ctx.scope.calls.append(cs)
        return cs

    # ---- string-keyed attribute access: getattr(obj, "name") and getattr(obj, "prefix" + x)
    def name_pattern(self, node) -> tuple:
        """What a name argument tells us: ("literal", s) for a known name, ("prefix", s) for a known
        start, ("unknown", "") otherwise."""
        if node.type == "string":
            if any(c.type == "interpolation" for c in node.children):
                parts = []
                for c in node.children:
                    if c.type == "interpolation":
                        break
                    if c.type == "string_content":
                        parts.append(self.txt(c))
                prefix = "".join(parts)
                return ("prefix", prefix) if prefix else ("unknown", "")
            try:
                value = ast.literal_eval(self.txt(node))
            except (ValueError, SyntaxError):
                return ("unknown", "")
            return ("literal", value) if isinstance(value, str) else ("unknown", "")
        if node.type == "binary_operator":
            op = node.child_by_field_name("operator")
            left = node.child_by_field_name("left")
            if op is not None and self.txt(op) == "+" and left is not None and left.type == "string":
                kind, text = self.name_pattern(left)
                if kind == "literal":
                    return ("prefix", text)
        return ("unknown", "")

    def dynamic_getattr(self, fn, args, ctx: Ctx) -> tuple:
        """For a call to the builtin getattr with a receiver that is a plain name or attribute:
        (receiver Shape, name pattern); otherwise ()."""
        if fn is None or fn.type != "identifier" or self.txt(fn) != "getattr" or args is None:
            return ()
        pos = [a for a in args.named_children if a.type not in ("comment", "keyword_argument")]
        if len(pos) < 2 or pos[0].type not in ("identifier", "attribute"):
            return ()
        receiver = self.shape(pos[0], ctx)
        if receiver.kind != "name":
            return ()
        return (receiver, self.name_pattern(pos[1]))

    # --------------------------------------------------------------- walk
    def children(self, node, ctx: Ctx):
        for c in node.children:
            self.visit(c, ctx)

    def visit(self, node, ctx: Ctx):
        h = getattr(self, "v_" + node.type, None)
        if h is not None:
            h(node, ctx)
        else:
            for c in node.children:
                self.visit(c, ctx)

    def v_type(self, node, ctx):          # annotations: nothing to collect
        return

    def v_comment(self, node, ctx):
        return

    def v_string(self, node, ctx):        # f-string interpolations hold code
        if any(c.type == "interpolation" for c in node.children):
            for c in node.children:
                if c.type == "interpolation":
                    self.visit(c, ctx)

    def v_decorated_definition(self, node, ctx):
        decos = [c for c in node.children if c.type == "decorator"]
        definition = node.child_by_field_name("definition")
        if definition is not None and definition.type == "function_definition":
            self.define_function(definition, ctx, decos)    # decorators are owned by the function
            return
        for d in decos:
            for c in d.children:
                if c.type != "@":
                    self.visit(c, ctx)        # calls inside decorator expressions
        if definition is None:
            return
        if definition.type == "class_definition":
            self.define_class(definition, ctx, decos)
        else:
            self.visit(definition, ctx)

    def v_function_definition(self, node, ctx):
        self.define_function(node, ctx, [])

    def v_class_definition(self, node, ctx):
        self.define_class(node, ctx, [])

    def v_if_statement(self, node, ctx):
        cond = node.child_by_field_name("condition")
        cons = node.child_by_field_name("consequence")
        tc = cond is not None and self.txt(cond).strip().endswith("TYPE_CHECKING") and "not " not in self.txt(cond)
        self.truthy(cond, ctx)
        for c in node.children:
            if cons is not None and c.id == cons.id and tc:
                old = ctx.tc
                ctx.tc = True
                self.visit(c, ctx)
                ctx.tc = old
            else:
                self.visit(c, ctx)

    def v_try_statement(self, node, ctx):
        old = ctx.in_try
        ctx.in_try = True
        self.children(node, ctx)
        ctx.in_try = old


    # ---- implicit protocol calls (operators, iteration, truthiness, ...)
    def implicit(self, kind: str, node, ctx: Ctx, names: tuple, first: bool = False):
        if node is None:
            return
        n = node
        while n.type == "parenthesized_expression":
            kids = [c for c in n.children if c.is_named]
            if len(kids) != 1:
                return
            n = kids[0]
        if n.type not in ("identifier", "attribute", "call", "await"):
            return
        for k, sh in self.value_shapes(n, ctx):
            if k != "val":
                continue
            ctx.scope.implicits.append(Implicit(
                n.start_point[0] + 1, n.start_point[1], kind, sh,
                sh.kind == "call" and not sh.attrs, ctx.scope_id, self.collapse(self.txt(n), 100),
                names, first))

    def truthy(self, node, ctx: Ctx):
        self.implicit("bool", node, ctx, ("__bool__", "__len__"), True)

    def record_value_refs(self, node, ctx: Ctx):
        """A name or attribute in a value position (assigned, returned, stored in a display) names an
        object without calling it: a function there is referenced by the enclosing scope."""
        if node is None:
            return
        t = node.type
        if t in ("identifier", "attribute"):
            sh = self.shape(node, ctx)
            if sh.kind == "name":
                ctx.scope.value_refs.append((node.start_point[0] + 1, node.start_point[1], sh))
        elif t == "parenthesized_expression":
            for c in node.named_children:
                self.record_value_refs(c, ctx)
        elif t in ("list", "tuple", "set"):
            for c in node.named_children:
                self.record_value_refs(c, ctx)
        elif t == "dictionary":
            for c in node.named_children:
                if c.type == "pair":
                    self.record_value_refs(c.child_by_field_name("value"), ctx)

    def _ret(self, node, ctx):
        f = ctx.func
        if f is None or ctx.kind != "func":
            return
        for c in node.children:
            if c.is_named and c.type not in ("comment",):
                for k, sh in self.value_shapes(c, ctx):
                    if k == "val":
                        f.return_shapes.append(sh)

    def v_return_statement(self, node, ctx):
        for c in node.named_children:
            self.record_value_refs(c, ctx)
        self._ret(node, ctx)
        self.children(node, ctx)

    def v_yield(self, node, ctx):
        self._ret(node, ctx)
        self.children(node, ctx)

    def v_while_statement(self, node, ctx):
        self.truthy(node.child_by_field_name("condition"), ctx)
        self.children(node, ctx)

    def v_elif_clause(self, node, ctx):
        self.truthy(node.child_by_field_name("condition"), ctx)
        self.children(node, ctx)

    def v_not_operator(self, node, ctx):
        self.truthy(node.child_by_field_name("argument"), ctx)
        self.children(node, ctx)

    def v_boolean_operator(self, node, ctx):
        self.truthy(node.child_by_field_name("left"), ctx)
        self.truthy(node.child_by_field_name("right"), ctx)
        self.children(node, ctx)

    def v_conditional_expression(self, node, ctx):
        kids = [c for c in node.children if c.is_named]
        if len(kids) >= 3:
            self.truthy(kids[1], ctx)
        self.children(node, ctx)

    def v_interpolation(self, node, ctx):
        expr = node.child_by_field_name("expression")
        conv = node.child_by_field_name("type_conversion")
        if expr is not None:
            if conv is not None and "r" in self.txt(conv):
                self.implicit("repr", expr, ctx, ("__repr__",), True)
            else:
                self.implicit("str", expr, ctx, ("__str__", "__repr__"), True)
        self.children(node, ctx)

    OPS = {"==": "__eq__", "!=": "__eq__", "<": "__lt__", ">": "__gt__", "<=": "__le__",
           ">=": "__ge__", "+": "__add__", "-": "__sub__", "*": "__mul__", "/": "__truediv__",
           "//": "__floordiv__", "%": "__mod__", "**": "__pow__", "@": "__matmul__",
           "&": "__and__", "|": "__or__", "^": "__xor__", "<<": "__lshift__", ">>": "__rshift__"}

    def v_comparison_operator(self, node, ctx):
        operands = [c for c in node.children if c.is_named]
        toks = " ".join(self.txt(c) for c in node.children if not c.is_named).split()
        if "in" in toks and operands:
            self.implicit("contains", operands[-1], ctx, ("__contains__",))
        for sym, dn in (("==", "__eq__"), ("!=", "__eq__"), ("<", "__lt__"), (">", "__gt__"),
                        ("<=", "__le__"), (">=", "__ge__")):
            if sym in toks:
                for o in operands:
                    self.implicit("cmp", o, ctx, (dn,))
        self.children(node, ctx)

    def v_binary_operator(self, node, ctx):
        op = node.child_by_field_name("operator")
        dn = self.OPS.get(self.txt(op)) if op is not None else None
        if dn:
            self.implicit("op", node.child_by_field_name("left"), ctx, (dn,))
        self.children(node, ctx)

    def v_subscript(self, node, ctx):
        mode = self.sub_mode
        self.sub_mode = "get"
        kind, names = {"get": ("getitem", ("__getitem__",)), "set": ("setitem", ("__setitem__",)),
                       "del": ("delitem", ("__delitem__",))}[mode]
        self.implicit(kind, node.child_by_field_name("value"), ctx, names)
        self.children(node, ctx)

    def v_delete_statement(self, node, ctx):
        for c in node.children:
            if c.type == "subscript":
                self.sub_mode = "del"
            self.visit(c, ctx)
            self.sub_mode = "get"

    # ---- imports
    def _dotted(self, n) -> str:
        return self.txt(n).replace(" ", "")

    def v_import_statement(self, node, ctx):
        names = []
        for c in node.children_by_field_name("name"):
            if c.type == "aliased_import":
                nm = self._dotted(c.child_by_field_name("name"))
                al = self.txt(c.child_by_field_name("alias"))
                names.append((nm, al))
            else:
                names.append((self._dotted(c), None))
        self._add_import(ImportRec("import", "", 0, names, False, self._imp_ctx(ctx),
                                   node.start_point[0] + 1, ctx.func.id if ctx.func else "",
                                   ctx.in_try), ctx)

    def v_import_from_statement(self, node, ctx):
        mod_node = node.child_by_field_name("module_name")
        level, module = 0, ""
        if mod_node is not None:
            if mod_node.type == "relative_import":
                for c in mod_node.children:
                    if c.type == "import_prefix":
                        level = self.txt(c).count(".")
                    elif c.type == "dotted_name":
                        module = self._dotted(c)
            else:
                module = self._dotted(mod_node)
        names, star = [], False
        for c in node.children_by_field_name("name"):
            if c.type == "aliased_import":
                names.append((self._dotted(c.child_by_field_name("name")),
                              self.txt(c.child_by_field_name("alias"))))
            else:
                names.append((self._dotted(c), None))
        if any(c.type == "wildcard_import" for c in node.children):
            star = True
        self._add_import(ImportRec("from", module, level, names, star, self._imp_ctx(ctx),
                                   node.start_point[0] + 1, ctx.func.id if ctx.func else "",
                                   ctx.in_try), ctx)

    def v_future_import_statement(self, node, ctx):
        return

    def _imp_ctx(self, ctx: Ctx) -> str:
        if ctx.tc:
            return "type_only"
        if ctx.func is not None:
            return "deferred"
        return "runtime"

    def _add_import(self, rec: ImportRec, ctx: Ctx):
        self.mod.imports.append(rec)
        if ctx.func is not None:
            ctx.func.imports.append(rec)
            for nm, al in rec.names:
                ctx.func.local_names.add(al or nm.split(".")[0])

    # ---- definitions
    def deco_names(self, decos) -> list:
        out = []
        for d in decos:
            e = [c for c in d.children if c.type != "@"]
            if not e:
                continue
            e = e[0]
            if e.type == "call":
                f = e.child_by_field_name("function")
                out.append(self._dotted(f))
            else:
                out.append(self._dotted(e))
        return out

    def _deco_call(self, decos, names: set):
        """Return the call node of the first decorator whose name is in `names`."""
        for d in decos:
            e = [c for c in d.children if c.type != "@"]
            if e and e[0].type == "call":
                f = e[0].child_by_field_name("function")
                if self._dotted(f) in names:
                    return e[0]
        return None

    def params_of(self, params_node):
        out = []
        self.defaults = {}
        if params_node is None:
            return out
        for c in params_node.children:
            t = c.type
            if t == "identifier":
                out.append((self.txt(c), None, False))
            elif t in ("typed_parameter",):
                nm = None
                for cc in c.children:
                    if cc.type == "identifier":
                        nm = self.txt(cc)
                        break
                    if cc.type in ("list_splat_pattern", "dictionary_splat_pattern"):
                        for ccc in cc.children:
                            if ccc.type == "identifier":
                                nm = self.txt(ccc)
                        break
                ann = c.child_by_field_name("type")
                if nm:
                    out.append((nm, self.txt(ann) if ann is not None else None, False))
            elif t == "default_parameter":
                nm = c.child_by_field_name("name")
                if nm is not None:
                    out.append((self.txt(nm), None, True))
                    self.defaults[self.txt(nm)] = self.txt(c.child_by_field_name("value")).strip()
            elif t == "typed_default_parameter":
                nm = c.child_by_field_name("name")
                ann = c.child_by_field_name("type")
                if nm is not None:
                    out.append((self.txt(nm), self.txt(ann) if ann is not None else None, True))
                    self.defaults[self.txt(nm)] = self.txt(c.child_by_field_name("value")).strip()
            elif t in ("list_splat_pattern", "dictionary_splat_pattern"):
                for cc in c.children:
                    if cc.type == "identifier":
                        out.append((self.txt(cc), None, False))
        return out

    def docstring(self, body, full: bool = False) -> str:
        if body is None or body.type != "block":
            return ""
        for c in body.children:
            if c.type == "comment":
                continue
            if c.type == "expression_statement" and c.named_child_count == 1 and \
                    c.named_children[0].type in ("string", "concatenated_string"):
                raw = self.txt(c.named_children[0])
                try:
                    v = ast.literal_eval(raw)
                    if isinstance(v, str):
                        return v.strip() if full else v.strip()[:1000]
                except Exception:
                    pass
                return raw.strip("\"' \n") if full else raw.strip("\"' \n")[:1000]
            break
        return ""

    def tokens(self, node, out: list, skip_def_bodies: bool = False):
        """Leaf-token stream without comments, docstrings or whitespace."""
        t = node.type
        if t == "comment":
            return
        if t == "string" or t == "concatenated_string":
            out.append(self.txt(node))
            return
        if t == "block" and node.parent is not None and node.parent.type in (
                "function_definition", "class_definition"):
            kids = list(node.children)
            i = 0
            while i < len(kids) and kids[i].type == "comment":
                i += 1
            if i < len(kids) and kids[i].type == "expression_statement" and \
                    kids[i].named_child_count == 1 and kids[i].named_children[0].type in (
                        "string", "concatenated_string"):
                kids.pop(i)
            for k in kids:
                self.tokens(k, out, skip_def_bodies)
            return
        if skip_def_bodies and t == "function_definition":
            out.append("<def>")
            for f in ("name", "parameters", "return_type"):
                n = node.child_by_field_name(f)
                if n is not None:
                    self.tokens(n, out, skip_def_bodies)
            return
        if node.child_count == 0:
            out.append(self.txt(node))
            return
        for c in node.children:
            self.tokens(c, out, skip_def_bodies)

    def define_function(self, node, ctx: Ctx, decos):
        name_node = node.child_by_field_name("name")
        name = self.txt(name_node)
        if ctx.kind == "func":
            qual = f"{ctx.qual}.<locals>.{name}"
        elif ctx.kind == "class":
            qual = f"{ctx.qual}.{name}"
        else:
            qual = name
        dn = self.deco_names(decos)
        is_setter = any(d.endswith(".setter") for d in dn)
        is_deleter = any(d.endswith(".deleter") for d in dn)
        suffix = "#setter" if is_setter else ("#deleter" if is_deleter else "")
        fid = self.uid(f"{self.path}::{qual}", suffix)
        is_async = any(c.type == "async" for c in node.children)
        params_node = node.child_by_field_name("parameters")
        ret = node.child_by_field_name("return_type")
        body = node.child_by_field_name("body")
        params = self.params_of(params_node)
        pdefaults = dict(self.defaults)
        in_class = ctx.kind == "class"
        f = FuncInfo(
            id=fid, name=name, qualname=qual, path=self.path,
            start=node.start_point[0] + 1, end=self.end_line(node),
            is_async=is_async, is_method=in_class, decorators=dn,
            returns=self.txt(ret) if ret is not None else None, params=params,
            class_id=ctx.cls.id if in_class and ctx.cls else None,
            parent_func=ctx.func.id if ctx.kind == "func" and ctx.func else None,
            is_nested=ctx.kind == "func",
        )
        f.param_defaults = pdefaults
        f.is_property = any(d in PROPERTY_DECOS for d in dn) or is_setter or is_deleter
        f.is_setter = is_setter
        f.is_abstract = any(d in ABSTRACT_DECOS for d in dn)
        f.is_staticmethod = "staticmethod" in dn
        f.is_classmethod = "classmethod" in dn
        f.is_overload = any(d in OVERLOAD_DECOS for d in dn)
        f.is_contextmanager = any(d in CM_DECOS for d in dn)
        f.is_fixture = any(d in FIXTURE_DECOS for d in dn)
        if f.is_fixture:
            call = self._deco_call(decos, FIXTURE_DECOS)
            f.fixture_name = name
            if call is not None:
                args = call.child_by_field_name("arguments")
                for a in (args.named_children if args is not None else []):
                    if a.type == "keyword_argument":
                        k = self.txt(a.child_by_field_name("name"))
                        v = self.txt(a.child_by_field_name("value"))
                        if k == "autouse" and v == "True":
                            f.fixture_autouse = True
                        if k == "name":
                            f.fixture_name = v.strip("\"'")
        for d in decos:
            e = [c for c in d.children if c.type != "@"]
            if e and e[0].type == "call" and self._dotted(
                    e[0].child_by_field_name("function")).endswith("usefixtures"):
                args = e[0].child_by_field_name("arguments")
                for a in (args.named_children if args is not None else []):
                    if a.type == "string":
                        f.usefixtures.append(self.txt(a).strip("\"'"))
        if self.is_test_file and not f.is_fixture:
            if ctx.kind == "module" and (name.startswith("test_") or name == "test"):
                f.is_test = True
            elif ctx.kind == "class" and ctx.cls is not None and ctx.cls.name.startswith("Test") \
                    and name.startswith("test"):
                f.is_test = True
        # parameters / first param
        if in_class and not f.is_staticmethod and params:
            f.first_param = params[0][0]
        for pname, pann, _d in params:
            f.local_names.add(pname)
            f.bindings.append(Binding(pname, "param", None, pann, f.start))
        # signature text
        ptxt = self.collapse(self.txt(params_node), 400) if params_node is not None else "()"
        f.signature = ("async " if is_async else "") + f"def {name}{ptxt}" + (
            f" -> {self.collapse(self.txt(ret), 120)}" if ret is not None else "")
        f.doc = self.docstring(body)
        # hashes
        f.body_hash = _h(self.txt(body)) if body is not None else ""
        toks: list = []
        if body is not None:
            self.tokens(body, toks)
        f.logic_hash = _h("\x00".join(toks))
        st: list = [dn and "|".join(dn) or "", name, "async" if is_async else ""]
        for d in decos:
            self.tokens(d, st)
        if params_node is not None:
            self.tokens(params_node, st)
        if ret is not None:
            self.tokens(ret, st)
        f.signature_hash = _h("\x00".join(st))
        f.text_hash = _h(self.txt(node))
        self.mod.funcs.append(f)
        # register names in enclosing scope
        if ctx.kind == "module":
            self.mod.top_defs[name] = ("func", fid)
            self.mod.local_names.add(name)
        elif ctx.kind == "func" and ctx.func is not None:
            ctx.func.local_names.add(name)
            ctx.func.nested_defs[name] = ("func", fid)
        # Decorators run when the definition executes, in the enclosing scope, and apply the
        # decorated function: `@d` is `d(f)`, `@d(args)` is `d(args)(f)`.  Both are recorded as
        # calls owned by the enclosing scope, with the function itself as their argument.
        for d in decos:
            expr = [c for c in d.children if c.type != "@"]
            if not expr:
                continue
            expr = expr[0]
            if expr.type == "attribute" and self.txt(expr.child_by_field_name("attribute")) in (
                    "setter", "getter", "deleter"):
                continue            # `@prop.setter` returns the property: no call happens
            if expr.type == "call":
                self.visit(expr, ctx)                      # the factory call and its arguments
                factory = self.callsite(expr, ctx)
                app_shape = Shape("call", "", (), factory, self.collapse(self.txt(expr), 120))
            else:
                app_shape = self.shape(expr, ctx)          # bare decorator: a name or attribute
            ctx.scope.calls.append(CallSite(
                line=d.start_point[0] + 1, col=d.start_point[1],
                end_line=d.end_point[0] + 1, raw=self.collapse(self.txt(d)),
                shape=app_shape, owner=ctx.scope_id,
                arg_names=(Shape("def", fid, (), None, qual),),
            ))
        # walk default values in the enclosing scope
        if params_node is not None:
            for c in params_node.children:
                if c.type in ("default_parameter", "typed_default_parameter"):
                    v = c.child_by_field_name("value")
                    if v is not None:
                        self.visit(v, ctx)
        # recurse into body
        if body is not None:
            inner = Ctx(scope=f, scope_id=fid, qual=qual, kind="func", cls=None, func=f,
                        tc=False, in_try=False)
            for c in body.children:
                self.visit(c, inner)

    def define_class(self, node, ctx: Ctx, decos):
        name = self.txt(node.child_by_field_name("name"))
        if ctx.kind == "func":
            qual = f"{ctx.qual}.<locals>.{name}"
        elif ctx.kind == "class":
            qual = f"{ctx.qual}.{name}"
        else:
            qual = name
        cid = self.uid(f"{self.path}::{qual}")
        bases, meta = [], None
        sup = node.child_by_field_name("superclasses")
        if sup is not None:
            for a in sup.named_children:
                if a.type == "keyword_argument":
                    if self.txt(a.child_by_field_name("name")) == "metaclass":
                        meta = self.txt(a.child_by_field_name("value"))
                else:
                    bases.append(self.collapse(self.txt(a), 120))
        c = ClassInfo(
            id=cid, name=name, qualname=qual, path=self.path,
            start=node.start_point[0] + 1, end=self.end_line(node),
            bases_raw=bases, decorators=self.deco_names(decos),
            is_nested=ctx.kind != "module",
            parent_func=ctx.func.id if ctx.func else None,
            parent_class=ctx.cls.id if ctx.kind == "class" and ctx.cls else None,
            is_test_class=self.is_test_file and name.startswith("Test"), metaclass=meta,
        )
        full_doc = self.docstring(node.child_by_field_name("body"), full=True)
        c.doc, c.doc_hash = full_doc[:1000], _h(full_doc)
        toks: list = []
        if node.child_by_field_name("body") is not None:
            self.tokens(node.child_by_field_name("body"), toks, skip_def_bodies=True)
        c.logic_hash = _h("\x00".join(toks))
        self.mod.classes.append(c)
        if ctx.kind == "module":
            self.mod.top_defs[name] = ("class", cid)
            self.mod.local_names.add(name)
        elif ctx.kind == "func" and ctx.func is not None:
            ctx.func.local_names.add(name)
            ctx.func.nested_defs[name] = ("class", cid)
        body = node.child_by_field_name("body")
        if body is not None:
            inner = Ctx(scope=ctx.scope, scope_id=ctx.scope_id, qual=qual, kind="class",
                        cls=c, func=ctx.func, tc=ctx.tc, in_try=ctx.in_try)
            for ch in body.children:
                self.visit(ch, inner)

    # ---- calls, attributes
    def v_call(self, node, ctx):
        fn = node.child_by_field_name("function")
        self.callsite(node, ctx)
        if fn is not None:
            base = self.peel(fn)
            if base.type == "call":
                self.v_call(base, ctx)
            elif base.type != "identifier":
                for c in base.children:
                    self.visit(c, ctx)
        args = node.child_by_field_name("arguments")
        if args is not None:
            self.visit(args, ctx)

    def v_attribute(self, node, ctx):
        sh = self.shape(node, ctx)
        ctx.scope.accesses.append(AttrAccess(node.start_point[0] + 1, node.start_point[1], sh,
                                             self.write_flag, ctx.scope_id))
        base = self.peel(node)
        if base.type == "call":
            self.v_call(base, ctx)
        elif base.type != "identifier":
            for c in base.children:
                self.visit(c, ctx)

    # ---- assignments / bindings
    def value_shapes(self, node, ctx: Ctx) -> list:
        """Possible value shapes for an expression used as the RHS of a binding."""
        out = []
        t = node.type
        if t == "parenthesized_expression":
            kids = [c for c in node.children if c.is_named]
            return self.value_shapes(kids[0], ctx) if len(kids) == 1 else []
        if t == "await":
            kids = [c for c in node.children if c.is_named]
            return self.value_shapes(kids[-1], ctx) if kids else []
        if t == "call":
            fn = node.child_by_field_name("function")
            fname = self._dotted(fn) if fn is not None else ""
            if fname in ("cast", "typing.cast", "t.cast"):
                args = node.child_by_field_name("arguments")
                if args is not None and args.named_child_count >= 1:
                    return [("ann", self.txt(args.named_children[0]))]
            out.append(("val", Shape("call", "", (), self.callsite(node, ctx), self.collapse(self.txt(node), 120))))
            return out
        if t in ("identifier", "attribute"):
            return [("val", self.shape(node, ctx))]
        if t == "yield":
            return [("yield", None)]
        if t == "tuple":
            # positional: a tuple display can be unpacked by position (`a, b = f()`)
            elems = []
            for c in node.named_children:
                sh = self.shape(c, ctx) if c.type in ("identifier", "attribute") else None
                elems.append(sh if sh is not None and sh.kind == "name" else None)
            if any(e is not None for e in elems):
                return [("val", Shape("tuple", elems=tuple(elems), raw=self.collapse(self.txt(node), 80)))]
            return out
        if t in ("dictionary", "list", "set"):
            elems = []
            for c in node.named_children:
                v = c.child_by_field_name("value") if c.type == "pair" else c
                if v is not None and v.type in ("identifier", "attribute"):
                    sh = self.shape(v, ctx)
                    if sh.kind == "name":
                        elems.append(sh)
            if elems:
                return [("val", Shape("coll", elems=tuple(elems), raw=self.collapse(self.txt(node), 80)))]
            return out
        if t == "subscript":
            v = node.child_by_field_name("value")
            if v is not None and v.type in ("identifier", "attribute", "call"):
                return [("val", Shape("index", inner=self.shape(v, ctx), raw=self.collapse(self.txt(node), 80)))]
            return out
        if t == "conditional_expression":
            kids = [c for c in node.children if c.is_named]
            if len(kids) >= 3:
                return self.value_shapes(kids[0], ctx) + self.value_shapes(kids[2], ctx)
        if t == "boolean_operator":
            left, right = node.child_by_field_name("left"), node.child_by_field_name("right")
            res = []
            for x in (left, right):
                if x is not None:
                    res += self.value_shapes(x, ctx)
            return res
        return out

    def rebind(self, name: str, ctx: Ctx):
        sc = ctx.scope
        sc.local_names.add(name)
        if isinstance(sc, FuncInfo):
            sc.rebound.add(name)

    def add_binding(self, name: str, kind: str, shape, ann, line, ctx: Ctx, is_async=False):
        sc = ctx.scope
        self.rebind(name, ctx)
        sc.bindings.append(Binding(name, kind, shape, ann, line, is_async))

    def bind_names(self, target, ctx: Ctx):
        """Record all identifiers in an assignment/for target as local (untyped)."""
        t = target.type
        if t == "identifier":
            self.rebind(self.txt(target), ctx)
        elif t in ("pattern_list", "tuple_pattern", "list_pattern", "tuple", "list",
                   "list_splat_pattern", "as_pattern_target"):
            for c in target.children:
                self.bind_names(c, ctx)
        elif t in ("attribute", "subscript"):
            self.visit(target, ctx)

    def v_assignment(self, node, ctx):
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        self.record_value_refs(right, ctx)
        typ = node.child_by_field_name("type")
        targets = [left]
        r = right
        while r is not None and r.type == "assignment":
            targets.append(r.child_by_field_name("left"))
            r = r.child_by_field_name("right")
        ann = self.txt(typ) if typ is not None else None
        vals = self.value_shapes(r, ctx) if r is not None else []
        line = node.start_point[0] + 1
        for tgt in targets:
            if tgt is None:
                continue
            if tgt.type == "identifier":
                name = self.txt(tgt)
                if ctx.kind == "class" and ctx.cls is not None:
                    if ann:
                        ctx.cls.attr_anns[name] = ann
                    for k, v in vals:
                        ctx.cls.attr_bindings.append(AttrBinding(
                            name, "ann" if k == "ann" else "val", None if k == "ann" else v,
                            v if k == "ann" else None, line))
                    continue
                self.rebind(name, ctx)
                if ctx.kind != "class":
                    if ann:
                        self.add_binding(name, "ann", None, ann, line, ctx)
                    for k, v in vals:
                        if k == "ann":
                            self.add_binding(name, "ann", None, v, line, ctx)
                        elif k == "yield":
                            self.add_binding(name, "yield", None, None, line, ctx)
                        else:
                            self.add_binding(name, "val", v, None, line, ctx)
                    # module-level special forms
                    if ctx.kind == "module" and r is not None:
                        self._module_special(name, r, ctx)
            elif tgt.type == "attribute":
                obj = tgt.child_by_field_name("object")
                attr = self.txt(tgt.child_by_field_name("attribute"))
                f = ctx.func
                if (ctx.kind == "func" and f is not None and f.is_method and obj is not None
                        and obj.type == "identifier" and self.txt(obj) == f.first_param):
                    if ann:
                        f.attr_bindings.append(AttrBinding(attr, "ann", None, ann, line))
                    for k, v in vals:
                        if k == "ann":
                            f.attr_bindings.append(AttrBinding(attr, "ann", None, v, line))
                        elif k == "val":
                            f.attr_bindings.append(AttrBinding(attr, "val", v, None, line))
                old = self.write_flag
                self.write_flag = True
                self.v_attribute(tgt, ctx)
                self.write_flag = old
            elif tgt.type == "subscript":
                self.sub_mode = "set"
                self.visit(tgt, ctx)
                self.sub_mode = "get"
            elif tgt.type in ("pattern_list", "tuple_pattern") and r is not None and len(targets) == 1:
                # `a, b = value`: each name is the element at its position in the value
                for i, c in enumerate(tgt.named_children):
                    if c.type == "identifier":
                        name = self.txt(c)
                        self.rebind(name, ctx)
                        for k, sh in vals:
                            if k == "val":
                                ctx.scope.bindings.append(Binding(name, "unpack", sh, None, line, False, i))
                self.bind_names(tgt, ctx)
            else:
                self.bind_names(tgt, ctx)
        if r is not None:
            self.visit(r, ctx)

    def _module_special(self, name: str, rhs, ctx: Ctx):
        if name == "__all__" and rhs.type in ("list", "tuple"):
            self.mod.all_names = [self._strlit(c) for c in rhs.named_children if c.type == "string"]
        if rhs.type == "call":
            fn = rhs.child_by_field_name("function")
            if fn is not None and self._dotted(fn).split(".")[-1] == "TypeVar":
                bound = ""
                args = rhs.child_by_field_name("arguments")
                for a in (args.named_children if args is not None else []):
                    if a.type == "keyword_argument" and self.txt(a.child_by_field_name("name")) == "bound":
                        bound = self.txt(a.child_by_field_name("value")).strip("\"'")
                self.mod.typevars[name] = bound

    def _strlit(self, n) -> str:
        try:
            return ast.literal_eval(self.txt(n))
        except Exception:
            return self.txt(n).strip("\"'")

    def v_augmented_assignment(self, node, ctx):
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        if (ctx.kind == "module" and left is not None and left.type == "identifier"
                and self.txt(left) == "__all__" and right is not None and right.type in ("list", "tuple")):
            self.mod.all_names = (self.mod.all_names or []) + [
                self._strlit(c) for c in right.named_children if c.type == "string"]
        if left is not None:
            if left.type == "identifier":
                self.rebind(self.txt(left), ctx)
            else:
                old = self.write_flag
                self.write_flag = True
                if left.type == "subscript":
                    self.sub_mode = "set"
                self.visit(left, ctx)
                self.sub_mode = "get"
                self.write_flag = old
        if right is not None:
            self.visit(right, ctx)

    def v_for_statement(self, node, ctx):
        left = node.child_by_field_name("left")
        is_async = any(c.type == "async" for c in node.children)
        self.implicit("aiter" if is_async else "iter", node.child_by_field_name("right"), ctx,
                      ("__aiter__", "__anext__") if is_async else ("__iter__", "__next__"))
        self._for_binding(left, node.child_by_field_name("right"), ctx)
        if left is not None:
            self.bind_names(left, ctx)
        for c in node.children:
            if left is not None and c.id == left.id:
                continue
            self.visit(c, ctx)

    def _for_binding(self, left, right, ctx):
        if left is None or right is None or ctx.kind == "class":
            return
        if left.type == "identifier":
            for k, sh in self.value_shapes(right, ctx):
                if k == "val":
                    self.add_binding(self.txt(left), "for", sh, None, left.start_point[0] + 1, ctx)
        elif left.type in ("pattern_list", "tuple_pattern"):
            names = [c for c in left.named_children]
            for i, c in enumerate(names):
                if c.type != "identifier":
                    continue
                for k, sh in self.value_shapes(right, ctx):
                    if k == "val":
                        ctx.scope.local_names.add(self.txt(c))
                        ctx.scope.bindings.append(Binding(self.txt(c), "for_unpack", sh, None,
                                                          c.start_point[0] + 1, False, i))

    def v_for_in_clause(self, node, ctx):
        self._for_binding(node.child_by_field_name("left"), node.child_by_field_name("right"), ctx)
        is_async = any(c.type == "async" for c in node.children)
        self.implicit("aiter" if is_async else "iter", node.child_by_field_name("right"), ctx,
                      ("__aiter__", "__anext__") if is_async else ("__iter__", "__next__"))
        for c in node.children:
            self.visit(c, ctx)

    def v_named_expression(self, node, ctx):
        nm = node.child_by_field_name("name")
        val = node.child_by_field_name("value")
        if nm is not None:
            self.rebind(self.txt(nm), ctx)
            if val is not None:
                for k, v in self.value_shapes(val, ctx):
                    if k == "val":
                        self.add_binding(self.txt(nm), "val", v, None, node.start_point[0] + 1, ctx)
        if val is not None:
            self.visit(val, ctx)

    def v_except_clause(self, node, ctx):
        for c in node.children:
            if c.type == "as_pattern":
                kids = [x for x in c.children if x.is_named]
                alias = c.child_by_field_name("alias")
                if kids and alias is not None and ctx.kind != "class":
                    ids = [x for x in alias.children if x.type == "identifier"]
                    te = kids[0]
                    names = [self.txt(x) for x in te.named_children] if te.type == "tuple" else [self.txt(te)]
                    if len(ids) == 1 and names:
                        self.add_binding(self.txt(ids[0]), "ann", None, " | ".join(names),
                                         node.start_point[0] + 1, ctx)
                for cc in c.children:
                    if cc.type == "as_pattern_target":
                        self.bind_names(cc, ctx)
                    else:
                        self.visit(cc, ctx)
            else:
                self.visit(c, ctx)

    def v_with_statement(self, node, ctx):
        is_async = any(c.type == "async" for c in node.children)
        clause = next((c for c in node.children if c.type == "with_clause"), None)
        items = clause.children if clause is not None else []
        for it in items:
            if it.type == "with_item":
                v = it.child_by_field_name("value")
            elif it.type in ("as_pattern",):
                v = it
            else:
                continue
            if v is None:
                continue
            expr, alias = v, None
            if v.type == "as_pattern":
                kids = [c for c in v.children if c.is_named]
                expr = kids[0]
                alias = v.child_by_field_name("alias")
            vs = self.value_shapes(expr, ctx)
            ln = expr.start_point[0] + 1
            for k, sh in vs:
                if k != "val":
                    continue
                ctx.scope.implicits.append(Implicit(
                    ln, expr.start_point[1], "async_with" if is_async else "with", sh,
                    sh.kind == "call" and not sh.attrs, ctx.scope_id, self.collapse(self.txt(expr), 100),
                    ("__aenter__", "__aexit__") if is_async else ("__enter__", "__exit__")))
                if alias is not None and alias.type == "as_pattern_target":
                    nm = [c for c in alias.children if c.type == "identifier"]
                    if len(nm) == 1 and alias.named_child_count == 1:
                        self.add_binding(self.txt(nm[0]), "with", sh, None, ln, ctx, is_async)
            if alias is not None:
                self.bind_names(alias, ctx)
            self.visit(expr, ctx)
        body = node.child_by_field_name("body")
        if body is not None:
            self.visit(body, ctx)


# ----------------------------------------------------------------------------- API
def package_predicates(files) -> tuple:
    """(has_init, has_py) for a set of repository-relative file paths.

    has_init(d): directory d is a regular package (has __init__.py).
    has_py(d):   directory d holds Python files, so it can be a namespace package (PEP 420).
    """
    file_set = set(files)
    py_dirs = {p.rsplit("/", 1)[0] if "/" in p else "" for p in file_set if p.endswith(".py")}

    def has_init(d: str) -> bool:
        return (d + "/__init__.py" if d else "__init__.py") in file_set

    def has_py(d: str) -> bool:
        return d in py_dirs

    return has_init, has_py


def module_name_for(path: str, has_init, has_py=None) -> tuple:
    """Dotted name and package for `path`.

    Walks up from the file's directory while a directory is a package (has __init__.py) or a
    namespace package (holds Python files), and stops at a source root such as `src/`, which
    holds neither.  `src/flask/sansio/app.py` is `flask.sansio.app`, as Python imports it.
    """
    parts = path.split("/")
    fname = parts[-1]
    stem = fname[:-3] if fname.endswith(".py") else fname
    dirs = parts[:-1]
    i = len(dirs)
    while i > 0:
        d = "/".join(dirs[:i])
        if has_init(d) or (has_py is not None and has_py(d)):
            i -= 1
        else:
            break
    pkg_parts = dirs[i:]
    if stem == "__init__":
        name = ".".join(pkg_parts)
        package = name
    else:
        name = ".".join(pkg_parts + [stem])
        package = ".".join(pkg_parts)
    return name, package


def extract_file(path: str, data: bytes, module_name: str = "", package: str = "") -> ModuleInfo:
    mod = ModuleInfo(
        id=path, path=path, name=module_name or path[:-3].replace("/", "."), package=package,
        is_test=is_test_path(path), is_init=path.endswith("__init__.py"),
    )
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        mod.decode_errors = True
    mod.nlines = data.count(b"\n") + (0 if data.endswith(b"\n") or not data else 1)
    mod.content_hash = _h(data.decode("utf-8", "replace"))
    parser = Parser(_LANG)
    tree = parser.parse(data)
    root = tree.root_node
    mod.partial = bool(root.has_error)
    w = Walker(path, data, mod)
    ctx = Ctx(scope=mod, scope_id=path, qual="", kind="module", cls=None, func=None)
    try:
        for c in root.children:
            w.visit(c, ctx)
    except RecursionError:
        mod.partial = True
    toks: list = []
    try:
        for c in root.children:
            if c is root.children[0] and c.type == "expression_statement" and c.named_child_count == 1 \
                    and c.named_children[0].type == "string":
                continue
            w.tokens(c, toks, skip_def_bodies=True)
    except RecursionError:
        pass
    mod.logic_hash = _h("\x00".join(toks))
    if mod.partial:
        stack = [root]
        while stack and len(mod.error_lines) < 20:
            n = stack.pop()
            if n.type == "ERROR" or n.is_missing:
                mod.error_lines.append(n.start_point[0] + 1)
                continue
            if n.has_error:
                stack.extend(reversed(n.children))
        mod.error_lines.sort()
    return mod
