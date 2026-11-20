"""Gaps the coverage check found on click: bare and factory decorators, property reads on
untyped receivers, and module-level __getattr__. Each is a call the static graph used to miss."""

from tests.helpers import build, targets

from unpack_graph.model import TIER_INFERRED


def test_decorators_are_applied_in_the_enclosing_scope():
    g = build("gaps")
    # the decorator runs when the module is imported, so the module owns the application
    assert "lib.py::register" in targets(g, "lib.py")
    assert "lib.py::factory.<locals>.decorator" in targets(g, "lib.py")
    # the decorated function is the argument: the decorator reaches it by reference
    assert "lib.py::bare_decorated" in targets(g, "lib.py")
    assert "lib.py::factory_decorated" in targets(g, "lib.py")


def test_bare_and_factory_decorators_are_reachable_through_the_import():
    g = build("gaps")
    assert g.reach["lib.py::register"].label in ("reached", "direct")
    assert g.reach["lib.py::bare_decorated"].label in ("reached", "direct")
    assert g.reach["lib.py::factory.<locals>.decorator"].label in ("reached", "direct")


def test_property_read_on_untyped_receiver_uses_the_unique_property():
    g = build("gaps")
    t = targets(g, "lib.py::Holder.describe")
    assert t["lib.py::Thing.label"].tier == TIER_INFERRED and t["lib.py::Thing.label"].via == "unique_name"
    assert g.reach["lib.py::Thing.label"].label in ("reached", "direct", "reached_uncertain")


def test_module_getattr_answers_a_missing_module_attribute():
    g = build("gaps")
    assert "lib.py::__getattr__" in targets(g, "test_lib.py::test_module_getattr")
    assert targets(g, "test_lib.py::test_module_getattr")["lib.py::__getattr__"].via == "module_getattr"
    assert g.reach["lib.py::__getattr__"].label in ("reached", "direct")


def test_factory_with_a_callable_annotation_still_returns_its_closure():
    # factory's annotation is typing.Callable[...], which names no class; the closure it returns
    # must still be applied, as in click's option/argument decorators
    g = build("gaps")
    assert "lib.py::factory.<locals>.decorator" in targets(g, "lib.py")


def test_property_read_reaches_overrides_of_the_declared_base():
    g = build("gaps")
    assert targets(g, "lib.py::count_sides")["lib.py::Shape.sides"].tier == TIER_INFERRED
    assert "lib.py::Square.sides" in targets(g, "lib.py::count_sides")
    assert g.reach["lib.py::Square.sides"].label in ("reached", "reached_uncertain")


def test_method_read_without_call_is_a_reference():
    g = build("gaps")
    t = targets(g, "lib.py::get_describer")
    assert t["lib.py::Thing.describe_me"].via == "method_ref"
    assert g.reach["lib.py::Thing.describe_me"].label in ("reached", "direct", "reached_uncertain")
