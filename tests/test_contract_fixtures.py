"""Hand-written UI fixtures must match the server contract and be internally consistent.

The graph page is built against these files (docs/ui-graph-plan.md §13). Each `done`
fixture is validated through AnalysisResponse, then checked for the references the
page relies on: every edge, reading-order id, impact hop, reason, finding and hunk
points at a node that exists, and the stats add up.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from server.app.schemas.api import AnalysisResponse

FIXTURES = Path(__file__).resolve().parent.parent / "contract" / "fixtures"
MAX_NODES = 200  # server/app/config.py MAX_GRAPH_NODES
MAX_EDGES = 500  # server/app/config.py MAX_GRAPH_EDGES


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def consistency_errors(data: dict) -> list[str]:
    errors: list[str] = []
    graph = data["graph"]
    nodes = {n["id"]: n for n in graph["nodes"]}
    if len(nodes) != len(graph["nodes"]):
        errors.append("duplicate node ids")
    non_container = [n for n in nodes.values() if n["layer"] != "container"]
    if len(non_container) > MAX_NODES:
        errors.append("too many nodes")
    if len(graph["edges"]) > MAX_EDGES:
        errors.append("too many edges")

    for n in nodes.values():
        if n.get("parent") and n["parent"] not in nodes:
            errors.append(f"{n['id']}: missing parent {n['parent']}")

    for e in graph["edges"]:
        for end in ("source", "target"):
            if e[end] not in nodes:
                errors.append(f"edge {e['id']}: {end} {e[end]} is not a node")
        if e["kind"] == "REACHES" and not nodes.get(e["source"], {}).get("is_test"):
            errors.append(f"edge {e['id']}: REACHES must start at a test")

    collapsed_ids = {i for g in graph["collapsed"] for i in g["node_ids"]}
    for g in graph["collapsed"]:
        if g["anchor"] not in nodes:
            errors.append(f"collapsed {g['id']}: anchor {g['anchor']} is not a node")

    for rid in data["reading_order"]:
        if rid not in nodes:
            errors.append(f"reading_order: {rid} is not a node")

    for anchor, hops in data["impact"]["by_node"].items():
        if anchor not in nodes:
            errors.append(f"impact anchor {anchor} is not a node")
        for hop in hops:
            if hop["id"] not in nodes and hop["id"] not in collapsed_ids:
                errors.append(f"impact hop {hop['id']} is neither a node nor collapsed")

    reason_keys = set(data["reasons"])
    for key in reason_keys - set(nodes):
        errors.append(f"reasons: {key} is not a node")

    finding_ids = {f["id"] for f in data["findings"]}
    for f in data["findings"]:
        for fn in f["functions"]:
            if fn not in nodes:
                errors.append(f"finding {f['id']}: {fn} is not a node")
    for n in nodes.values():
        for fid in n["finding_ids"]:
            if fid not in finding_ids:
                errors.append(f"{n['id']}: finding {fid} does not exist")

    for key in data["diff_hunks"]:
        if key not in nodes:
            errors.append(f"diff_hunks: {key} is not a node")

    for turn in data["timeline"]:
        for nid in turn["nodes"]:
            if nid not in nodes:
                errors.append(f"timeline {turn['turn']}: {nid} is not a node")

    for n in nodes.values():
        test = n.get("test")
        if not test:
            continue
        for step in test["shortest_path"]:
            if step not in nodes:
                errors.append(f"{n['id']}: test path step {step} is not a node")

    changed = [n for n in nodes.values() if n.get("change")]
    stats = data["stats"]
    if stats["functions_changed"] != len(changed):
        errors.append("stats.functions_changed does not match changed nodes")
    if sum(stats["by_change"].values()) != stats["functions_changed"]:
        errors.append("stats.by_change does not add up")
    if sum(stats["by_source"].values()) != stats["functions_changed"]:
        errors.append("stats.by_source does not add up")
    unreached = [n for n in changed if n["test"] and n["test"]["label"] == "none"]
    if stats["not_reached_by_tests"] != len(unreached):
        errors.append("stats.not_reached_by_tests does not match changed nodes with label none")
    return errors


DONE_FIXTURES = ["analysis_graph_rich.json", "analysis_no_session.json"]


@pytest.mark.parametrize("name", DONE_FIXTURES)
def test_done_fixture_matches_contract(name: str) -> None:
    data = load(name)
    AnalysisResponse.model_validate(data)
    assert consistency_errors(data) == []


@pytest.mark.xfail(strict=True, reason="analysis_done.json predates the consistency rules; see docs/ui-graph-plan.md §2.4")
def test_existing_done_fixture_is_consistent() -> None:
    data = load("analysis_done.json")
    assert consistency_errors(data) == []


def test_running_fixture_shape() -> None:
    data = load("analysis_running.json")
    assert set(data) == {"analysis"}
    assert data["analysis"]["status"] in {"queued", "running"}
    assert data["analysis"]["public_id"]


def test_failed_fixture_shape() -> None:
    data = load("analysis_failed.json")
    assert data["analysis"]["status"] == "failed"
    assert data["analysis"]["error_code"]
    assert data["analysis"]["error_message"]
    assert {"repo", "branch", "head_sha", "short_sha"} <= set(data)
