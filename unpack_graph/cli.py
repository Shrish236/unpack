"""CLI for unpack_graph."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .diff import detect_changes
from .graph import build_graph
from .region import build_region
from .source import FsSource, GitSource


def main() -> None:
    parser = argparse.ArgumentParser(prog="unpack-graph", description="Unpack code knowledge graph CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # build
    build_p = subparsers.add_parser("build", help="Build code graph for repository")
    build_p.add_argument("repo", help="Path to repository")
    build_p.add_argument("--rev", help="Git revision (optional)")
    build_p.add_argument("--neo4j", action="store_true", help="Load into Neo4j")

    # changed
    changed_p = subparsers.add_parser("changed", help="Detect changed functions between revisions")
    changed_p.add_argument("repo", help="Path to repository")
    changed_p.add_argument("base", help="Base git revision")
    changed_p.add_argument("head", help="Head git revision")
    changed_p.add_argument("--json", action="store_true", help="Output as JSON")

    # region
    region_p = subparsers.add_parser("region", help="Build GraphView region for a diff")
    region_p.add_argument("repo", help="Path to repository")
    region_p.add_argument("base", help="Base git revision")
    region_p.add_argument("head", help="Head git revision")
    region_p.add_argument("--cap", type=int, default=15, help="Neighbor cap")
    region_p.add_argument("--tests-per-node", type=int, default=5, help="Tests per node")
    region_p.add_argument("--out", help="Write JSON to output file")

    args = parser.parse_args()

    if args.command == "build":
        repo_path = Path(args.repo).resolve()
        src = GitSource(repo_path, args.rev) if args.rev else FsSource(repo_path)
        g = build_graph(src)
        summary = {
            "modules": len(g.modules),
            "classes": len(g.classes),
            "functions": len(g.functions),
            "edges": len(g.edges),
            "tests": sum(1 for f in g.functions.values() if f.is_test),
        }
        print(json.dumps(summary, indent=2))
        if args.neo4j:
            from .neo4j_io import get_neo4j_driver, load_graph
            driver = get_neo4j_driver()
            load_graph(driver, g)
            print("Successfully loaded graph into Neo4j.")

    elif args.command == "changed":
        cs = detect_changes(args.repo, args.base, args.head)
        if args.json:
            out = {
                fid: {"kind": ci.kind, "flags": ci.flags, "head_lines": ci.head_lines}
                for fid, ci in cs.changed_functions.items()
            }
            print(json.dumps(out, indent=2))
        else:
            print(f"Changed functions ({len(cs.changed_functions)}):")
            for fid, ci in cs.changed_functions.items():
                print(f"  [{ci.kind.upper()}] {fid} (flags: {', '.join(ci.flags)})")

    elif args.command == "region":
        cs = detect_changes(args.repo, args.base, args.head)
        view = build_region(cs, cap=args.cap, tests_per_node=args.tests_per_node)
        formatted = json.dumps(view, indent=2)
        if args.out:
            Path(args.out).write_text(formatted, encoding="utf-8")
            print(f"GraphView written to {args.out}")
        else:
            print(formatted)


if __name__ == "__main__":
    main()
