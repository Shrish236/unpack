"""String-keyed attribute access: getattr(obj, "name") and getattr(obj, "prefix" + x).

These are how a method dispatches to handlers by name (a visitor over node types, for example).
Static analysis without them reports every handler as untested, which is a false `none`.
"""

from tests.helpers import build, targets

from unpack_graph.model import TIER_AMBIGUOUS, TIER_INFERRED


def test_literal_name_resolves_to_that_method():
    g = build("dynamic")
    t = targets(g, "m.py::Walker.visit_literal")
    assert t["m.py::Walker.v_one"].tier == TIER_INFERRED and t["m.py::Walker.v_one"].via == "getattr"


def test_known_prefix_reaches_every_method_starting_with_it_as_ambiguous():
    g = build("dynamic")
    t = targets(g, "m.py::Walker.visit")
    for handler in ("m.py::Walker.v_one", "m.py::Walker.v_two"):
        assert t[handler].tier == TIER_AMBIGUOUS and t[handler].via == "getattr_prefix"
    # only the receiver's class, and only names with the prefix
    assert "m.py::Other.v_three" not in t
    assert "m.py::Walker.not_handler" not in t


def test_unknown_name_adds_no_dispatch_edges():
    g = build("dynamic")
    t = targets(g, "m.py::Walker.visit_unknown")
    assert not any(dst.startswith("m.py::Walker.v_") for dst in t)


def test_handlers_and_their_callees_are_reachable_not_none():
    g = build("dynamic")
    # v_one is reached on a certain path through visit_literal; its callee _helper transitively
    assert g.reach["m.py::Walker.v_one"].label == "reached"
    assert g.reach["m.py::Walker._helper"].label == "reached"
    # v_two is only reachable through the ambiguous prefix edge: uncertain, never none
    assert g.reach["m.py::Walker.v_two"].label == "reached_uncertain"
    # not matched by the prefix and not called by any test: the one true none
    assert g.reach["m.py::Walker.not_handler"].label == "none"
    assert g.reach["m.py::Other.v_three"].label == "none"
