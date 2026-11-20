"""Section 9 corners: resolution (pass 2)."""
from tests.helpers import build, edge, targets

from unpack_graph.model import TIER_AMBIGUOUS, TIER_EXTRACTED, TIER_INFERRED


def site(g, path, raw_prefix):
    return [s for s in g.sites if s.path == path and s.kind == "call" and s.raw.startswith(raw_prefix)]


# ---------------------------------------------------------------- imports / re-exports
def test_import_forms_and_reexports():
    g = build("imports")
    ub = "pkg/a/b.py::use_relative"
    t = targets(g, ub)
    assert "pkg/core.py::helper" in t                     # from ..core import helper as h ; pkg.core.helper()
    assert "pkg/core.py::Core.__init__" in t
    assert "pkg/types.py::mine" in t                      # from .. import types as pkg_types
    assert "pkg/a/sibling.py::sib" in t                   # from . import sibling
    assert "pkg/sub/deep.py::Deep.run" in t               # import pkg.sub.deep as dd
    assert "pkg/core.py::Core.run" in t                   # import pkg.core as c ; c.Core().run()
    assert all(e.tier == TIER_EXTRACTED for k, e in t.items() if k in ("pkg/core.py::helper", "pkg/types.py::mine"))


def test_absolute_import_via_ancestor_directory():
    g = build("imports")
    assert "pkg/a/sibling.py::sib" in targets(g, "pkg/a/b.py::use_abs_sibling")


def test_reexport_chain_star_all_and_stdlib_shadowing():
    g = build("imports")
    t = targets(g, "pkg/user.py::use")
    assert "pkg/core.py::Core.__init__" in t              # pkg.Core() via star import + __all__
    assert "pkg/core.py::helper" in t
    assert "pkg/core.py::Core.run" in t
    assert "pkg/sub/deep.py::Deep.run" in t              # pkg.sub.Deep() through sub/__init__
    # re-export chain of 4 hops (Thing: r1 -> r2 -> r3 -> r4 -> r5) exceeds the 3-hop limit
    assert "pkg/r5.py::Thing.__init__" not in t
    # typing / types must stay external even though pkg/typing.py and pkg/types.py exist
    assert "pkg/typing.py::cast" not in t and "pkg/types.py::mine" not in t
    st = site(g, "pkg/user.py", "typing.cast")[0]
    assert st.status == "external"
    assert site(g, "pkg/user.py", "types.SimpleNamespace")[0].status == "external"
    # star import from a module that does not exist stays harmless
    assert site(g, "pkg/user.py", "not_exported")[0].status in ("resolved", "unresolved", "external")


def test_star_import_respects___all__():
    g = build("imports")
    t = targets(g, "pkg/relative_all.py::star_user")
    assert "pkg/core.py::helper" in t and "pkg/core.py::Core.__init__" in t
    assert "pkg/core.py::not_exported" not in t           # not in core.__all__
    t3 = targets(g, "pkg/relative_all.py::star_without_all")
    assert "pkg/sub/deep.py::Deep.run" in t3                       # `from .sub.deep import *`, module without __all__
    t2 = targets(g, "pkg/relative_all.py::local_import")
    assert "pkg/core.py::helper" in t2                    # deferred import inside a function


def test_import_edges_have_context_and_names():
    g = build("imports")
    e = {(i.src, i.dst, i.context): i for i in g.imports}
    assert ("pkg/a/b.py", "pkg/core.py", "runtime") in e
    assert "helper as h" in e[("pkg/a/b.py", "pkg/core.py", "runtime")].names
    assert ("pkg/relative_all.py", "pkg/core.py", "deferred") in e
    assert ("pkg/user.py", "pkg/typing.py", "runtime") not in e


# ---------------------------------------------------------------- inheritance
def test_self_super_cls_inheritance_and_via():
    g = build("inherit")
    t = targets(g, "m.py::C.use")
    e = t["m.py::A.only_on_a"]
    assert e.tier == TIER_INFERRED and e.via == "inherit:m.py::A"      # grandparent method
    assert t["m.py::B.shared"].tier == TIER_EXTRACTED or t["m.py::B.shared"].tier == TIER_INFERRED
    assert t["m.py::B.shared"].via == "inherit:m.py::B"
    sb = targets(g, "m.py::B.shared")
    assert sb["m.py::A.shared"].tier == TIER_EXTRACTED                  # super() -> direct parent
    t2 = targets(g, "m.py::C.make")
    assert "m.py::A.only_on_a" in t2 and "m.py::A.__init__" in t2         # cls.m() and cls() -> inherited __init__
    assert t2["m.py::A.__init__"].tier == TIER_INFERRED
    assert targets(g, "m.py::C.init_chain")["m.py::A.only_on_a"].tier == TIER_INFERRED
    assert targets(g, "m.py::D.__init__")["m.py::A.__init__"].tier == TIER_INFERRED   # super().__init__() skips C/B
    assert ("m.py::B", "m.py::A") in g.inherits and ("m.py::C", "m.py::B") in g.inherits


# ---------------------------------------------------------------- local type inference
def test_local_type_inference_forms():
    g = build("types")
    for fn in ("f1", "f2", "f4", "f5", "f6"):
        t = targets(g, f"m.py::{fn}")
        assert "m.py::Cls.m" in t, fn
        assert t["m.py::Cls.m"].tier == TIER_INFERRED, fn
    assert "m.py::Cls.__enter__" in targets(g, "m.py::f2")                 # with-statement protocol
    assert "m.py::Cls.__exit__" in targets(g, "m.py::f2")
    t3 = targets(g, "m.py::f3")
    assert "m.py::ACls.am" in t3 and "m.py::ACls.__aenter__" in t3          # async with
    assert "m.py::Cls.m" in targets(g, "m.py::f7")                          # c.helper().m(): return-annotation chaining
    assert "m.py::Cls.m" in targets(g, "m.py::f8")
    assert "m.py::Holder.run" not in targets(g, "m.py::f8")
    t9 = targets(g, "m.py::f9")
    assert "m.py::Cls.m" in t9                                              # h.c.m() with self.c typed in __init__
    hr = targets(g, "m.py::Holder.run")
    assert "m.py::Cls.m" in hr and hr["m.py::Cls.m"].tier == TIER_INFERRED   # self.c / self.made typed in __init__
    assert "m.py::Cls.helper" in targets(g, "m.py::f7")


def test_unknown_receiver_unique_name_and_unresolved():
    g = build("types")
    s = site(g, "m.py", "unknown.m")[0]
    # `m` exists on one class only but is a builtin-ish short name? (not) -> INFERRED via unique_name
    assert s.status in ("resolved", "ambiguous")
    g2 = build("ambig")
    a = site(g2, "m.py", "x.get")[0]
    assert a.status == "ambiguous" and set(a.candidates) == {"m.py::Client.get", "m.py::AsyncClient.get", "m.py::Headers.get"}
    e = edge(g2, "m.py::f", "m.py::Client.get")
    assert e.tier == TIER_AMBIGUOUS and len(e.candidates) == 3
    u = site(g2, "m.py", "x.only_here")[0]
    assert u.status == "resolved" and u.targets[0].via == "unique_name" and u.targets[0].tier == TIER_INFERRED
    n = site(g2, "m.py", "x.nothing_like_this")[0]
    assert n.status == "unresolved"                                          # never dropped
    assert any("nothing_like_this" in raw for _l, raw, _r in g2.unresolved["m.py::f"])
    # a typed receiver is NOT ambiguous even though `get` is defined on three classes
    assert targets(g2, "m.py::g")["m.py::Client.get"].tier == TIER_INFERRED


def test_abstract_dispatch_and_overrides():
    g = build("dispatch")
    t = targets(g, "m.py::use")
    assert t["m.py::Base.run"].tier == TIER_INFERRED
    assert t["m.py::Impl1.run"].via == "dispatch" and t["m.py::Impl2.run"].via == "dispatch"
    assert t["m.py::Impl1.run"].tier == TIER_INFERRED
    assert "m.py::Unrelated.run" not in t
    assert ("m.py::Impl1.run", "m.py::Base.run") in g.overrides and ("m.py::Impl2.run", "m.py::Base.run") in g.overrides
    tc = targets(g, "m.py::use_concrete")
    assert "m.py::Impl1.run" in tc and "m.py::Impl2.run" not in tc and "m.py::Base.run" not in tc


# ---------------------------------------------------------------- containers, enums, import-time, protocols
def test_registry_dict_of_classes_and_dict_items():
    g = build("containers")
    t = targets(g, "m.py::make")
    assert t["m.py::A.__init__"].via == "table" and t["m.py::B.__init__"].via == "table"
    assert t["m.py::A.__init__"].tier == TIER_INFERRED
    use = targets(g, "m.py::Holder.use")
    assert use["m.py::Pat.matches"].tier == TIER_INFERRED          # for pat, a in self.mounts.items()
    assert "m.py::A.__init__" in use                               # for a2 in self.mounts.values()
    assert "m.py::Pat.__lt__" in use                               # sorted(self.mounts.items()) compares keys
    assert "m.py::A.__init__" in targets(g, "m.py::Many.go")       # for item in self.build() -> List["A"]


def test_enum_members_and_metaclass_new():
    g = build("containers")
    assert "m.py::Color.__str__" in targets(g, "m.py::show")       # str(Color.RED)
    e = edge(g, "m.py", "m.py::Color.__new__")
    assert e is not None and e.via == "enum_metaclass"             # called by EnumMeta at class creation


def test_yield_send_type_and_except_as_binding():
    g = build("flow")
    t = targets(g, "m.py::auth_flow")
    assert t["m.py::Resp.ok"].tier == TIER_INFERRED            # response = yield req  ->  Generator[Req, Resp, None]
    assert "m.py::Resp.cookies" in t                            # property read on the sent value
    h = targets(g, "m.py::guarded")
    assert "m.py::Err.hook" in h                                # except (Err, ValueError) as exc / except Err as other
    assert "m.py::Err.request#setter" in h                      # exc.request = ... -> setter


def test_pytest_raises_excinfo_value_is_the_exception():
    g = build("flow")
    assert "m.py::Err.hook" in targets(g, "m.py::test_excinfo")
