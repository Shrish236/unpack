"""Indexed queries answer the same facts as the graph they were built from."""

from unpack_graph.graph import build_graph
from unpack_graph.query import GraphIndex
from unpack_graph.source import FsSource


def _index(tmp_path):
    (tmp_path / "lib.py").write_text(
        "class Base:\n"
        "    def run(self):\n"
        "        return 1\n\n\n"
        "class Impl(Base):\n"
        "    def run(self):\n"
        "        return helper() + 1\n\n\n"
        "def helper():\n"
        "    return 2\n\n\n"
        "def dead():\n"
        "    return 3\n"
    )
    (tmp_path / "test_lib.py").write_text(
        "from lib import Impl, helper\n\n\n"
        "def test_impl():\n"
        "    assert Impl().run() == 3\n\n\n"
        "def test_helper():\n"
        "    assert helper() == 2\n"
    )
    g = build_graph(FsSource(str(tmp_path)))
    return GraphIndex(g)


def test_find_by_name_and_qualname(tmp_path):
    ix = _index(tmp_path)
    assert "lib.py::helper" in ix.find("helper")
    assert ix.find("lib.py::Impl") == ["lib.py::Impl"]
    assert "lib.py::Impl.run" in ix.find("Impl.run")


def test_node_reports_label_and_reaching_tests(tmp_path):
    ix = _index(tmp_path)
    n = ix.node("lib.py::helper")
    assert n["kind"] == "function" and n["label"] == "direct"
    assert n["reached_by"] == 2 and n["uncertain_reached_by"] == 0


def test_tests_for_lists_depth_and_test(tmp_path):
    ix = _index(tmp_path)
    tests = ix.tests_for("lib.py::helper")
    assert [(t["test"], t["depth"]) for t in tests] == [("test_lib.py::test_helper", 1),
                                                        ("test_lib.py::test_impl", 2)]
    assert ix.tests_for("lib.py::helper", limit=1)[0]["test"] == "test_lib.py::test_helper"


def test_callers_and_callees_filter_tests(tmp_path):
    ix = _index(tmp_path)
    prod = [c["id"] for c in ix.callers("lib.py::helper")]
    assert prod == ["lib.py::Impl.run"]
    everything = [c["id"] for c in ix.callers("lib.py::helper", production_only=False)]
    assert "test_lib.py::test_helper" in everything
    assert [c["id"] for c in ix.callees("lib.py::Impl.run")] == ["lib.py::helper"]


def test_overrides_and_class_hierarchy(tmp_path):
    ix = _index(tmp_path)
    assert ix.overrides("lib.py::Impl.run")["overrides"] == ["lib.py::Base.run"]
    assert ix.overrides("lib.py::Base.run")["overridden_by"] == ["lib.py::Impl.run"]
    info = ix.class_info("lib.py::Impl")
    assert info["bases"] == ["lib.py::Base"]
    assert ix.class_info("lib.py::Base")["subclasses"] == ["lib.py::Impl"]


def test_untested_lists_only_production_none(tmp_path):
    ix = _index(tmp_path)
    # Base.run is never called: Impl.run overrides it and the tests call Impl().run()
    assert ix.untested_in("lib.py") == ["lib.py::Base.run", "lib.py::dead"]
    assert "lib.py::helper" not in ix.untested
    assert ix.untested_in("other/") == []
