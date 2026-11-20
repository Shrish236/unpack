"""The measurements: extraction against ast, resolution statistics, and the coverage comparison."""

import os

from tests.helpers import FIX, build

from unpack_graph.evaluate import compare_with_coverage, coverage_vs_ast, reach_summary, resolution_stats
from unpack_graph.graph import build_graph
from unpack_graph.source import FsSource


def test_coverage_vs_ast_is_complete_on_fixtures():
    root = os.path.join(FIX, "inherit")
    g = build_graph(FsSource(root))
    cov = coverage_vs_ast(root, g)
    assert cov["coverage_pct"] == 100.0
    assert cov["files_with_mismatch"] == []
    assert cov["ast_definitions"] == cov["found_definitions"] > 0


def test_resolution_stats_partition_every_call_site():
    g = build("types")
    stats = resolution_stats(g)
    total = stats["call_sites"]["total"]
    assert total == sum(stats["call_sites"]["counts"].values())
    assert stats["production"]["total"] + stats["tests"]["total"] == total
    assert sum(v["total"] for v in stats["by_shape"].values()) == total


def test_reach_summary_labels_production_functions():
    g = build("pytest_fx")
    summary = reach_summary(g)
    assert summary["production_functions"] == sum(summary["labels"].values())
    assert "lib.py::Client.untested" in summary["none"]
    assert "lib.py::Client.get" not in summary["none"]


def _synthetic_coverage(g, executed_fids):
    """A coverage.py-shaped report that executes every body line of the given functions."""
    files = {}
    for fid, f in g.funcs.items():
        if g.mods[f.path].is_test:
            continue
        entry = files.setdefault(f.path, {"executed_lines": [], "missing_lines": []})
        lines = list(range(f.start + 1, f.end + 1))
        if fid in executed_fids:
            entry["executed_lines"] += lines
        else:
            entry["missing_lines"] += lines
    return {"files": files}


def test_compare_with_coverage_counts_false_none_and_true_none():
    g = build("pytest_fx")
    untested = "lib.py::Client.untested"
    assert g.reach[untested].label == "none"
    # Execute the untested function: the `none` label becomes a false none.
    cov = compare_with_coverage(g, _synthetic_coverage(g, {untested}))
    assert untested in cov["false_none"]
    # Not executing it keeps the label correct.
    cov = compare_with_coverage(g, _synthetic_coverage(g, set()))
    assert untested not in cov["false_none"]
    assert cov["true_none"] >= 1 and cov["none_precision"] == 1.0


def test_empty_sample_reports_null_not_zero():
    g = build("pytest_fx")
    cov = compare_with_coverage(g, {"files": {}})
    assert cov["functions_compared"] == 0
    assert cov["none_precision"] is None and cov["untested_recall"] is None
