"""Module names follow Python's import rules: packages, namespace subpackages, and source roots."""

from tests.helpers import build

from unpack_graph.extract import module_name_for, package_predicates


def _names(paths):
    has_init, has_py = package_predicates(paths)
    return {p: module_name_for(p, has_init, has_py) for p in paths}


def test_namespace_subpackage_inside_a_package_keeps_its_name():
    names = _names(["src/flask/sansio/app.py", "src/flask/app.py", "src/flask/__init__.py"])
    assert names["src/flask/sansio/app.py"] == ("flask.sansio.app", "flask.sansio")
    assert names["src/flask/app.py"] == ("flask.app", "flask")
    assert names["src/flask/__init__.py"] == ("flask", "flask")


def test_source_root_is_not_part_of_the_name():
    names = _names(["src/pkg/mod.py", "src/pkg/__init__.py"])
    assert names["src/pkg/mod.py"] == ("pkg.mod", "pkg")


def test_relative_import_resolves_through_a_namespace_subpackage():
    g = build("namespace")
    sub = g.mods["src/pkg/sub/mod.py"]
    assert (sub.name, sub.package) == ("pkg.sub.mod", "pkg.sub")
    # `Top()` resolves to the class in the sibling module (no __init__, so no edge; the site says so)
    site = [s for s in g.sites if s.path == "src/pkg/sub/mod.py" and s.kind == "call" and s.raw == "Top()"]
    assert site and site[0].status == "no_init"


def test_import_through_a_top_level_dir_without_init_reaches_the_code_from_tests():
    """`server/` holds no Python files itself, so its modules are named `app.x`, but `import server.app.x` works."""
    g = build("rootpkg")
    assert g.mods["shop/app/pricing.py"].name == "app.pricing"
    assert g.reach["shop/app/pricing.py::apply_discount"].label == "direct"
    assert g.reach["shop/app/pricing.py::untested_helper"].label == "none"
