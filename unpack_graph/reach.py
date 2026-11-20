"""Test reachability computation across the code knowledge graph."""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, Any

from .model import ReachInfo, ReachLabel

if TYPE_CHECKING:
    from .graph import Graph

MAX_DEPTH = 12


def compute_reach(graph: Graph) -> dict[str, ReachInfo]:
    """Compute reachability from tests to production functions via BFS over CALLS edges."""
    res: dict[str, ReachInfo] = {}

    test_funcs = [f for f in graph.functions.values() if f.is_test]
    prod_funcs = [f for f in graph.functions.values() if not f.is_test]

    # Initialize prod functions with label "none"
    for f in prod_funcs:
        res[f.id] = ReachInfo(
            label="none",
            count=0,
            min_depth=None,
            path=[],
            tests=[],
            unresolved_hint=0,
        )

    # Initialize test functions with label "test"
    for f in test_funcs:
        res[f.id] = ReachInfo(
            label="test",
            count=0,
            min_depth=0,
            path=[f.id],
            tests=[],
            unresolved_hint=0,
        )

    # Adjacency map: source -> list of (target, tier)
    adj: dict[str, list[tuple[str, str | None]]] = {}
    for edge in graph.edges:
        if edge.kind == "CALLS":
            adj.setdefault(edge.source, []).append((edge.target, edge.tier))

    # Run BFS from each test
    for test in test_funcs:
        queue: deque[tuple[str, int, list[str], bool]] = deque([(test.id, 0, [test.id], False)])
        visited: dict[str, int] = {test.id: 0}

        while queue:
            curr_id, depth, path, is_uncertain = queue.popleft()

            if depth > 0 and curr_id in res:
                info = res[curr_id]
                if info.label != "test":
                    info.count += 1
                    if info.min_depth is None or depth < info.min_depth:
                        info.min_depth = depth
                        info.path = path

                    # Update label: direct vs reached vs reached_uncertain
                    new_label: ReachLabel = "reached_uncertain" if is_uncertain else ("direct" if depth == 1 else "reached")
                    if info.label == "none" or (info.label == "reached_uncertain" and not is_uncertain):
                        info.label = new_label

                    info.tests.append({"id": test.id, "depth": depth})

            if depth >= MAX_DEPTH:
                continue

            for target_id, tier in adj.get(curr_id, []):
                next_uncertain = is_uncertain or (tier == "AMBIGUOUS")
                if target_id not in visited or depth + 1 < visited[target_id]:
                    visited[target_id] = depth + 1
                    queue.append((target_id, depth + 1, path + [target_id], next_uncertain))

    return res
