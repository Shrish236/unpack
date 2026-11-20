"""Command line interface: `unpack-graph <command>`.

Commands:

  extract <repo> [--rev REV] [--check-ast] [--list]
      Pass 1 only: parse every .py file and report the functions and classes found.
      --check-ast compares every definition's (start, end, name) with Python's `ast` module.
      --list prints one line per definition.

  build <repo> [--rev REV]
      Passes 1 and 2: the call graph with a confidence tier on every edge.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import Counter

from .extract import extract_file, module_name_for
from .graph import build_graph
from .source import FsSource, GitSource


def _source(repo: str, rev: str | None):
    return GitSource(repo, rev) if rev else FsSource(repo)


def extract_all(src) -> dict:
    files = src.list_files()
    known = set(files)
    mods = {}
    for path in files:
        name, package = module_name_for(path, lambda x: x in known)
        mods[path] = extract_file(path, src.read(path), name, package)
    return mods


def ast_check(src, mods: dict) -> dict:
    """Compare pass-1 definitions with the `ast` module, file by file."""
    checked = 0
    mismatches = []
    for path, mod in mods.items():
        try:
            tree = ast.parse(src.read(path))
        except (SyntaxError, ValueError):
            continue  # files Python itself cannot parse are reported as partial elsewhere
        expected = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                expected.add(("function", node.lineno, node.end_lineno, node.name))
            elif isinstance(node, ast.ClassDef):
                expected.add(("class", node.lineno, node.end_lineno, node.name))
        found = {("function", f.start, f.end, f.name) for f in mod.funcs}
        found |= {("class", c.start, c.end, c.name) for c in mod.classes}
        checked += len(expected)
        if expected != found:
            mismatches.append({
                "path": path,
                "missing": sorted(map(str, expected - found))[:10],
                "extra": sorted(map(str, found - expected))[:10],
            })
    return {"definitions_checked": checked, "files_with_mismatch": mismatches}


def summary(mods: dict) -> dict:
    funcs = [f for m in mods.values() for f in m.funcs]
    classes = [c for m in mods.values() for c in m.classes]
    return {
        "files": len(mods),
        "functions": len(funcs),
        "methods": sum(1 for f in funcs if f.is_method),
        "nested_functions": sum(1 for f in funcs if f.is_nested),
        "async_functions": sum(1 for f in funcs if f.is_async),
        "classes": len(classes),
        "test_functions": sum(1 for f in funcs if f.is_test),
        "imports": sum(len(m.imports) for m in mods.values()),
        "partial_files": sorted(m.path for m in mods.values() if m.partial),
        "non_utf8_files": sorted(m.path for m in mods.values() if m.decode_errors),
    }


def cmd_extract(args) -> int:
    src = _source(args.repo, args.rev)
    mods = extract_all(src)
    if args.list:
        for path in sorted(mods):
            m = mods[path]
            for f in sorted(m.funcs, key=lambda x: x.start):
                kind = "async def" if f.is_async else "def"
                print(f"{path}:{f.start}-{f.end}  {kind} {f.qualname}")
            for c in sorted(m.classes, key=lambda x: x.start):
                print(f"{path}:{c.start}-{c.end}  class {c.qualname}")
    out = {"source": src.label, "summary": summary(mods)}
    if args.check_ast:
        out["ast_check"] = ast_check(src, mods)
    print(json.dumps(out, indent=2))
    if args.check_ast and out["ast_check"]["files_with_mismatch"]:
        return 1
    return 0


def graph_summary(g) -> dict:
    sites = Counter(f"{s.kind}:{s.status}" for s in g.sites)
    tiers = Counter(e.tier for e in g.calls.values())
    return {
        "source": g.label,
        "modules": len(g.mods),
        "functions": len(g.funcs),
        "classes": len(g.classes),
        "call_edges": len(g.calls),
        "call_edges_by_tier": dict(tiers),
        "inherits": len(g.inherits),
        "overrides": len(g.overrides),
        "imports": len(g.imports),
        "sites": dict(sites),
        "unresolved_functions": len(g.unresolved),
        "partial_files": sorted(m.path for m in g.mods.values() if m.partial),
        "timing_s": {k: round(v, 3) for k, v in g.timing.items()},
    }


def cmd_build(args) -> int:
    g = build_graph(_source(args.repo, args.rev))
    print(json.dumps(graph_summary(g), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="unpack-graph", description="Unpack code knowledge graph CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    ex = sub.add_parser("extract", help="parse every Python file and summarise definitions (pass 1)")
    ex.add_argument("repo", help="repository root (working tree)")
    ex.add_argument("--rev", default=None, help="read a git revision instead of the working tree")
    ex.add_argument("--check-ast", action="store_true", help="verify definitions against Python's ast")
    ex.add_argument("--list", action="store_true", help="print every definition")
    ex.set_defaults(func=cmd_extract)

    bd = sub.add_parser("build", help="build the call graph with confidence tiers (passes 1 and 2)")
    bd.add_argument("repo", help="repository root (working tree)")
    bd.add_argument("--rev", default=None, help="read a git revision instead of the working tree")
    bd.set_defaults(func=cmd_build)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
