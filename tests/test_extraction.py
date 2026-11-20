"""Section 9 corners: extraction (pass 1)."""
import ast
import os

from tests.helpers import FIX, build, extract_tree

from unpack_graph.extract import extract_file


def ids(g):
    return {f.qualname for f in g.funcs.values()}


def test_defs_everywhere_and_nothing_from_strings():
    g = build("extract")
    q = ids(g)
    expected = {
        "top", "top.<locals>.inner", "top.<locals>.inner.<locals>.deeper", "top.<locals>.LocalCls.m",
        "Outer.Inner.im", "Outer.method", "Outer.prop", "Outer.prop", "Outer.sm", "Outer.cm", "Outer.ctx",
        "Outer.abstract", "Outer.am", "in_if", "in_else", "in_try", "in_except", "docstring_fn",
        "decorator", "decorated_fn", "only_for_type_checkers",
    }
    assert expected <= q
    for fake in ("fake", "not_a_function", "not_real", "also_not_real"):
        assert fake not in q
    assert {c.qualname for c in g.classes.values()} >= {"Outer", "Outer.Inner", "Decorated", "top.<locals>.LocalCls"}


def test_flags_and_property_setter_ids_are_unique():
    g = build("extract")
    f = {x.id.split("::")[1]: x for x in g.funcs.values()}
    assert f["Outer.prop"].is_property and not f["Outer.prop"].is_setter
    assert f["Outer.prop#setter"].is_property and f["Outer.prop#setter"].is_setter
    assert f["Outer.sm"].is_staticmethod and f["Outer.sm"].first_param is None
    assert f["Outer.cm"].is_classmethod and f["Outer.cm"].first_param == "cls"
    assert f["Outer.ctx"].is_contextmanager
    assert f["Outer.abstract"].is_abstract
    assert f["Outer.am"].is_async and f["Outer.am"].is_method
    assert f["top.<locals>.inner"].is_nested and not f["top.<locals>.inner"].is_method
    assert f["decorated_fn"].decorators == ["decorator"]
    assert f["Outer.method"].start < f["Outer.method"].end


def test_ast_equivalence_on_every_fixture_file():
    n = 0
    for dp, _d, fns in os.walk(FIX):
        for fn in fns:
            if fn.endswith(".py") and "broken" not in dp:
                p = os.path.join(dp, fn)
                src = open(p, "rb").read()
                rel = os.path.relpath(p, FIX).replace(os.sep, "/")
                m = extract_file(rel, src)
                a = set()
                for node in ast.walk(ast.parse(src)):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        a.add(("f", node.lineno, node.end_lineno, node.name))
                    elif isinstance(node, ast.ClassDef):
                        a.add(("c", node.lineno, node.end_lineno, node.name))
                b = {("f", f.start, f.end, f.name) for f in m.funcs} | {("c", c.start, c.end, c.name) for c in m.classes}
                assert a == b, rel
                n += 1
    expected = sum(1 for dp, _d, fns in os.walk(FIX) for fn in fns if fn.endswith(".py") and "broken" not in dp)
    assert n == expected > 0


def test_import_records_and_contexts():
    src = b'''
from __future__ import annotations
import a.b
import a.b as c
from .x import y
from ..x.y import z as w
from . import mod
from m import (
    one,
    two as three,
)
from star import *
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .only_types import T
def f():
    import deferred_mod
    from .d import e
'''
    m = extract_file("pkg/sub/f.py", src, "pkg.sub.f", "pkg.sub")
    recs = {(r.kind, r.module, r.level, tuple(r.names), r.star, r.context) for r in m.imports}
    assert ("import", "", 0, (("a.b", None),), False, "runtime") in recs
    assert ("import", "", 0, (("a.b", "c"),), False, "runtime") in recs
    assert ("from", "x", 1, (("y", None),), False, "runtime") in recs
    assert ("from", "x.y", 2, (("z", "w"),), False, "runtime") in recs
    assert ("from", "", 1, (("mod", None),), False, "runtime") in recs
    assert ("from", "m", 0, (("one", None), ("two", "three")), False, "runtime") in recs
    assert ("from", "star", 0, (), True, "runtime") in recs
    assert ("from", "only_types", 1, (("T", None),), False, "type_only") in recs
    assert ("import", "", 0, (("deferred_mod", None),), False, "deferred") in recs
    assert ("from", "d", 1, (("e", None),), False, "deferred") in recs
    assert not any(r.module == "__future__" or "annotations" in [n for n, _ in r.names] for r in m.imports)


def test_class_bases_raw_and_all():
    src = b'import typing\nclass A(typing.Generic[T], BaseClient, abc.ABC, metaclass=M):\n    x: int\n__all__ = ["A", "b"]\n__all__ += ["c"]\n'
    m = extract_file("m.py", src)
    c = m.classes[0]
    assert c.bases_raw == ["typing.Generic[T]", "BaseClient", "abc.ABC"] and c.metaclass == "M"
    assert c.attr_anns == {"x": "int"}
    assert m.all_names == ["A", "b", "c"]


def test_hashes_text_vs_logic_vs_signature():
    base = b'def f(a, b=1):\n    """doc"""\n    # c\n    return a + b\n'
    doc = b'def f(a, b=1):\n    """other doc"""\n    # changed comment\n\n    return a + b\n'
    logic = b'def f(a, b=1):\n    return a - b\n'
    sig = b'def f(a, b=2):\n    return a + b\n'
    deco = b'@x\ndef f(a, b=1):\n    return a + b\n'
    fb, fd, fl, fs, fx = [extract_file("m.py", s).funcs[0] for s in (base, doc, logic, sig, deco)]
    assert fb.logic_hash == fd.logic_hash and fb.body_hash != fd.body_hash and fb.signature_hash == fd.signature_hash
    assert fb.logic_hash != fl.logic_hash
    assert fb.signature_hash != fs.signature_hash and fb.logic_hash == fs.logic_hash
    assert fb.signature_hash != fx.signature_hash        # decorators are part of the signature


def test_syntax_error_partial_non_utf8_empty_and_long(tmp_path):
    (tmp_path / "ok.py").write_text("def ok():\n    pass\n")
    (tmp_path / "bad.py").write_text("def good():\n    pass\n\ndef broken(:\n    pass\n\ndef after():\n    pass\n")
    (tmp_path / "latin.py").write_bytes(b"# caf\xe9 \xff\ndef latin():\n    return '\xe9'\n")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "long.py").write_text("".join(f"def fn_{i}(x):\n    return x + {i}\n\n" for i in range(5000)))
    g = extract_tree(str(tmp_path))
    assert g.mods["bad.py"].partial and g.mods["bad.py"].error_lines
    assert {f.name for f in g.mods["bad.py"].funcs} >= {"good", "after"}      # partial tree still yields defs
    assert not g.mods["ok.py"].partial
    assert g.mods["latin.py"].decode_errors and [f.name for f in g.mods["latin.py"].funcs] == ["latin"]
    assert g.mods["pkg/__init__.py"].nlines == 0 and not g.mods["pkg/__init__.py"].funcs
    assert len(g.mods["long.py"].funcs) == 5000


def test_end_line_ignores_trailing_comments_like_ast():
    src = b"def f():\n    x = 1\n    # trailing comment inside the block\n\n\nclass K:\n    def m(self):\n        pass\n        # tail\n"
    m = extract_file("m.py", src)
    assert {(f.name, f.start, f.end) for f in m.funcs} == {("f", 1, 2), ("m", 7, 8)}
    assert [(c.name, c.start, c.end) for c in m.classes] == [("K", 6, 8)]
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            assert any(n.end_lineno == x.end for x in m.funcs + m.classes)
