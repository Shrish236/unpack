"""Measurements of a built graph: extraction against `ast`, resolution statistics, reachability.

Nothing here is specific to one repository.  The checks answer:

* does pass 1 find every definition Python's own parser finds (coverage against `ast`)?
* how are call sites classified, overall and for production code and test code?
* how many production functions does each reachability label cover?
"""

from __future__ import annotations

import ast
import time
from collections import Counter, defaultdict

from .graph import build_graph
from .source import FsSource


def coverage_vs_ast(root: str, g) -> dict:
    """Every definition found by `ast` should be found by pass 1, with the same line range."""
    src = FsSource(root)
    totals = Counter()
    mismatches = []
    for path in src.list_files():
        try:
            tree = ast.parse(src.read(path))
        except (SyntaxError, ValueError):
            totals["files_not_parsed_by_ast"] += 1
            continue
        expected = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                expected.add(("function", node.lineno, node.end_lineno, node.name))
            elif isinstance(node, ast.ClassDef):
                expected.add(("class", node.lineno, node.end_lineno, node.name))
        mod = g.mods[path]
        found = {("function", f.start, f.end, f.name) for f in mod.funcs}
        found |= {("class", c.start, c.end, c.name) for c in mod.classes}
        totals["files"] += 1
        totals["ast_definitions"] += len(expected)
        totals["found_definitions"] += len(expected & found)
        if expected != found:
            mismatches.append({"path": path,
                               "missing": sorted(map(str, expected - found))[:10],
                               "extra": sorted(map(str, found - expected))[:10]})
    total = totals["ast_definitions"]
    return {
        "files": totals["files"],
        "files_not_parsed_by_ast": totals["files_not_parsed_by_ast"],
        "ast_definitions": total,
        "found_definitions": totals["found_definitions"],
        "coverage_pct": round(100.0 * totals["found_definitions"] / total, 3) if total else 100.0,
        "files_with_mismatch": mismatches,
    }


def resolution_stats(g) -> dict:
    """Call-site classes, split into production code and test code, and by call shape."""

    def bucket(s) -> str:
        if s.status == "resolved":
            prim = [t for t in s.targets if t.via not in ("dispatch",)
                    and not (t.via or "").startswith("property")]
            return "EXTRACTED" if any(t.tier == "EXTRACTED" for t in prim) else "INFERRED"
        return {"ambiguous": "AMBIGUOUS", "unresolved": "UNRESOLVED", "external": "EXTERNAL",
                "builtin": "BUILTIN", "no_init": "NO_INIT"}[s.status]

    order = ["EXTRACTED", "INFERRED", "AMBIGUOUS", "UNRESOLVED", "EXTERNAL", "BUILTIN", "NO_INIT"]
    calls = [s for s in g.sites if s.kind == "call"]

    def table(rows):
        counts = Counter(bucket(s) for s in rows)
        n = len(rows)
        return {"total": n, "counts": {k: counts.get(k, 0) for k in order},
                "pct": {k: round(100.0 * counts.get(k, 0) / n, 1) if n else 0.0 for k in order}}

    def is_test(path):
        return g.mods[path].is_test

    by_shape = defaultdict(list)
    for s in calls:
        by_shape[s.shape_cat].append(s)
    return {
        "call_sites": table(calls),
        "production": table([s for s in calls if not is_test(s.path)]),
        "tests": table([s for s in calls if is_test(s.path)]),
        "by_shape": {k: table(v) for k, v in sorted(by_shape.items())},
        "unresolved_reasons": dict(Counter(s.reason for s in calls if s.status == "unresolved")),
        "ambiguous_reasons": dict(Counter(s.reason for s in calls if s.status == "ambiguous")),
        "call_edges": len(g.calls),
        "call_edges_by_tier": dict(Counter(e.tier for e in g.calls.values())),
    }


def reach_summary(g) -> dict:
    """Reachability labels for production functions, and the functions labelled none."""
    prod = [f for f in g.funcs.values() if not g.mods[f.path].is_test]
    labels = Counter(g.reach[f.id].label for f in prod)
    none = sorted(f.id for f in prod if g.reach[f.id].label == "none")
    depth = Counter(g.reach[f.id].min_depth for f in prod if g.reach[f.id].label in ("direct", "reached"))
    return {
        "production_functions": len(prod),
        "labels": {k: labels.get(k, 0) for k in ("direct", "reached", "reached_uncertain", "none")},
        "none": none,
        "depth_histogram": {str(k): v for k, v in sorted(depth.items())},
        "test_functions": sum(1 for f in g.funcs.values() if f.is_test),
    }


def compare_with_coverage(g, coverage: dict) -> dict:
    """Compare static labels with a coverage.py JSON report (`coverage json`).

    A production function counts as executed when any line of its body (after the `def` line)
    ran in the tests.  `false_none` counts functions labelled `none` that did run: the failure
    the `none` flag must not have.  Functions without executable body lines are skipped.
    """
    files = coverage.get("files", {})
    rows = []
    skipped = Counter()
    for fid, f in g.funcs.items():
        if g.mods[f.path].is_test:
            continue
        info = files.get(f.path)
        if info is None:
            skipped["no_coverage_data"] += 1
            continue
        executed = set(info.get("executed_lines", []))
        missing = set(info.get("missing_lines", []))
        body = range(f.start + 1, f.end + 1)
        n_exec = sum(1 for ln in body if ln in executed)
        n_miss = sum(1 for ln in body if ln in missing)
        if n_exec + n_miss == 0:
            skipped["no_executable_body_lines"] += 1
            continue
        rows.append((fid, g.reach[fid].label, n_exec > 0))
    false_none = sorted(fid for fid, label, ran in rows if label == "none" and ran)
    true_none = sorted(fid for fid, label, ran in rows if label == "none" and not ran)
    never_ran = sum(1 for _f, _l, ran in rows if not ran)
    tested = [(fid, ran) for fid, label, ran in rows if label in ("direct", "reached")]
    return {
        "functions_compared": len(rows),
        "skipped": dict(skipped),
        "labels_when_executed": dict(Counter(label for _f, label, ran in rows if ran)),
        "labels_when_not_executed": dict(Counter(label for _f, label, ran in rows if not ran)),
        "false_none": false_none,
        "true_none": len(true_none),
        # null when no `none` label was compared, so an empty sample is not reported as 0% precise
        "none_precision": (round(len(true_none) / (len(true_none) + len(false_none)), 4)
                           if (true_none or false_none) else None),
        "never_executed": never_ran,
        "untested_recall": round(len(true_none) / never_ran, 4) if never_ran else None,
        "tested_but_never_executed": sum(1 for _f, ran in tested if not ran),
    }


def evaluate_repo(root: str) -> dict:
    t0 = time.time()
    g = build_graph(FsSource(root))
    build_s = time.time() - t0
    return {
        "root": root,
        "build_s": round(build_s, 3),
        "timing_s": {k: round(v, 3) for k, v in g.timing.items()},
        "coverage_vs_ast": coverage_vs_ast(root, g),
        "resolution": resolution_stats(g),
        "reachability": reach_summary(g),
    }
