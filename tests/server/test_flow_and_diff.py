"""File-level hunks with owners, the deterministic flow, and checking of the model's flow."""

from __future__ import annotations

import pytest

from server.app.llm.budget import LLMBudget
from server.app.llm.client import LLMFlowOutput, LLMFlowStage, LLMFlowStep, RawLLMResponse
from server.app.llm.flow import build_flow_prompt, run_flow, verify_flow
from server.app.pipeline.diff_files import build_diff_files
from server.app.pipeline.flow import build_flow, deterministic_flow
from server.app.pipeline.payload import parse_diff_hunks

DIFF = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1,2 +1,3 @@
+import os
 x = 1
 y = 2
@@ -10,3 +11,3 @@ def f():
-    return 1
+    return 2
 # end
@@ -30,2 +31,2 @@ class K:
-    z = 1
+    z = 2
diff --git a/gone.py b/gone.py
deleted file mode 100644
--- a/gone.py
+++ /dev/null
@@ -1,2 +0,0 @@
-def old():
-    pass
diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-a
+b
"""


def node(nid, path, label, layer="changed", kind="function", start=1, end=1):
    return {"id": nid, "path": path, "label": label, "layer": layer, "kind": kind, "start_line": start, "end_line": end}


GRAPH_NODES = [
    node("a.py", "a.py", "a.py", "container", "file", None, None),
    node("a.py::f", "a.py", "f", start=10, end=14),
    node("a.py::K", "a.py", "K", "container", "class", 28, 40),
    node("gone.py::old", "gone.py", "old", "ghost", start=1, end=2),
]
FILES = [
    {"path": "a.py", "status": "M"}, {"path": "gone.py", "status": "D"}, {"path": "README.md", "status": "M"},
    {"path": "logo.png", "status": "M", "is_binary": True},
]


def test_hunk_owners_cover_every_kind():
    files, per_node = build_diff_files(FILES, parse_diff_hunks(DIFF), GRAPH_NODES)
    by = {f["path"]: f for f in files}
    a = by["a.py"]["hunks"]
    assert [(h["owner_kind"], h["owners"]) for h in a] == [
        ("module", ["a.py"]),  # the import: no function covers it
        ("function", ["a.py::f"]),
        ("class", ["a.py::K"]),
    ]
    assert by["a.py"]["added"] == 3 and by["a.py"]["removed"] == 2
    # A deleted function owns the removed lines through the OLD side of the diff.
    assert by["gone.py"]["hunks"][0]["owners"] == ["gone.py::old"] and by["gone.py"]["status"] == "D"
    # Non-Python files keep their hunks with no node; a binary file has no patch at all.
    assert by["README.md"]["hunks"][0]["owner_kind"] == "file" and by["README.md"]["hunks"][0]["owners"] == []
    assert by["logo.png"]["no_patch"] and by["logo.png"]["hunks"] == []
    # The per-function view is derived from the same hunks and carries their ids.
    assert [h["id"] for h in per_node["a.py::f"]] == ["a.py#1"]
    assert "gone.py::old" in per_node


def test_hunk_over_two_functions_is_listed_once_with_both_owners():
    nodes = [node("m.py::a", "m.py", "a", start=1, end=5), node("m.py::b", "m.py", "b", start=6, end=9)]
    diff = "diff --git a/m.py b/m.py\n--- a/m.py\n+++ b/m.py\n@@ -4,4 +4,4 @@\n-x\n+y\n"
    files, per_node = build_diff_files([{"path": "m.py", "status": "M"}], parse_diff_hunks(diff), nodes)
    assert len(files[0]["hunks"]) == 1
    assert files[0]["hunks"][0]["owners"] == ["m.py::a", "m.py::b"]
    assert set(per_node) == {"m.py::a", "m.py::b"}


def test_empty_diff():
    assert build_diff_files([], {}, []) == ([], {})


def graph(nodes, calls):
    return {"nodes": nodes, "edges": [{"id": f"{a}>{b}", "source": a, "target": b, "kind": "CALLS"} for a, b in calls]}


def test_deterministic_flow_groups_call_chains_and_lists_everything():
    ns = [node(i, p, i.split("::")[1], start=n) for n, (i, p) in enumerate(
        [("a.py::entry", "a.py"), ("a.py::mid", "a.py"), ("b.py::leaf", "b.py"), ("c.py::alone", "c.py")], start=1)]
    ns.append(node("d.py::gone", "d.py", "gone", "ghost"))
    g = graph(ns, [("a.py::entry", "a.py::mid"), ("a.py::mid", "b.py::leaf")])
    flow = deterministic_flow(g, ["a.py::entry", "a.py::mid", "b.py::leaf", "c.py::alone", "d.py::gone"])
    assert [s["title"] for s in flow["stages"]] == ["Starts at entry", "Changes in c.py", "Removed"]
    assert flow["order"] == ["a.py::entry", "a.py::mid", "b.py::leaf", "c.py::alone", "d.py::gone"]


def test_deterministic_flow_survives_cycles_and_missing_reading_order():
    ns = [node("a.py::p", "a.py", "p", start=1), node("a.py::q", "a.py", "q", start=5)]
    flow = deterministic_flow(graph(ns, [("a.py::p", "a.py::q"), ("a.py::q", "a.py::p")]), [])  # not in reading_order
    assert sorted(flow["order"]) == ["a.py::p", "a.py::q"] and len(flow["stages"]) == 1


def llm_graph():
    ns = [node(f"a.py::f{i}", "a.py", f"f{i}", start=i * 10, end=i * 10 + 5) for i in (1, 2, 3)]
    ns.append(node("a.py::dead", "a.py", "dead", "ghost"))
    return graph(ns, [("a.py::f1", "a.py::f2"), ("a.py::f2", "a.py::f3")])


def out(*stages):
    return LLMFlowOutput(stages=[LLMFlowStage(title=t, steps=[LLMFlowStep(fn=f) for f in fns]) for t, fns in stages])


def test_verify_flow_drops_unknown_and_repeated_and_appends_missing():
    g = llm_graph()
    det = deterministic_flow(g, ["a.py::f1", "a.py::f2", "a.py::f3", "a.py::dead"])["order"]
    _, _, labels = build_flow_prompt(g, det, {}, "task")
    variant, warnings = verify_flow(out(("One", ["F2", "F9", "F2"]), ("", ["F1"])), labels, g, det)
    assert [s["node_ids"] for s in variant["stages"]][:2] == [["a.py::f2"], ["a.py::f1"]]
    assert variant["stages"][1]["title"] == "Stage 2"
    # f3 was never placed: it is appended, and the deleted function closes the flow.
    assert variant["order"] == ["a.py::f2", "a.py::f1", "a.py::f3", "a.py::dead"]
    assert sorted(variant["order"]) == sorted(det)
    assert any("unknown or repeated" in w for w in warnings) and any("not placed" in w for w in warnings)
    assert any("against this order" in w for w in warnings)  # f2 before its caller f1


def test_verify_flow_with_nothing_usable_is_none():
    g = llm_graph()
    det = deterministic_flow(g, ["a.py::f1", "a.py::f2", "a.py::f3"])["order"]
    _, _, labels = build_flow_prompt(g, det, {}, "t")
    variant, warnings = verify_flow(out(("X", ["F8"])), labels, g, det)
    assert variant is None and warnings


def test_prompt_labels_and_edges():
    g = llm_graph()
    det = deterministic_flow(g, ["a.py::f1", "a.py::f2", "a.py::f3"])["order"]
    _, user, labels = build_flow_prompt(g, det, {"a.py::f2": {"reason": "added a retry"}}, "make it retry")
    assert labels == {"F1": "a.py::f1", "F2": "a.py::f2", "F3": "a.py::f3"}
    assert "why: added a retry" in user and "calls: F3; called by: F1" in user and "make it retry" in user


class _Fake:
    def __init__(self, text):
        self.text, self.calls = text, 0

    async def generate_json(self, **kw):
        self.calls += 1
        return RawLLMResponse(text=self.text, model="m", input_tokens=10, output_tokens=5)


@pytest.mark.asyncio
async def test_run_flow_paths():
    from server.app.llm.client import set_llm_client
    g = llm_graph()
    det = deterministic_flow(g, ["a.py::f1", "a.py::f2", "a.py::f3"])["order"]
    fake = _Fake('{"stages":[{"title":"A","steps":[{"fn":"F1","role":"entry"},{"fn":"F2"},{"fn":"F3"}]}]}')
    set_llm_client(fake)
    try:
        budget = LLMBudget()
        res = await run_flow(g, det, {}, "t", budget)
        assert res.variant["order"][:3] == ["a.py::f1", "a.py::f2", "a.py::f3"] and budget.used == 15
        # One function: nothing to order, no call is made.
        one = graph([node("a.py::f1", "a.py", "f1")], [])
        assert (await run_flow(one, ["a.py::f1"], {}, "t", LLMBudget())).variant is None and fake.calls == 1
        # A used-up quota skips the call.
        res = await run_flow(g, det, {}, "t", LLMBudget(quota_hit=True))
        assert res.variant is None and res.quota and fake.calls == 1
    finally:
        set_llm_client(None)


def test_build_flow_without_llm():
    flow = build_flow(llm_graph(), ["a.py::f1"], warnings=None)
    assert flow["llm"] is None and flow["deterministic"]["order"]


# ---- decisions: nodes and outcomes ----

from server.app.pipeline.decision_links import attach_nodes_and_outcomes  # noqa: E402
from server.app.pipeline.decisions import verify_decisions  # noqa: E402


def dec(turn, actor, kind, **kw):
    return {"turn": turn, "actor": actor, "kind": kind, "type": "design", "quote": kw.pop("quote", ""), "proposal": "",
            "rule_followed": kw.pop("rule_followed", None), **kw}


def test_nodes_follow_the_next_edit_and_outcomes_by_rule():
    nodes = [node("a.py::f", "a.py", "f"), node("a.py::g", "a.py", "g"), node("b.py::h", "b.py", "h")]
    timeline = [
        {"turn": "T3", "kind": "edit", "nodes": ["a.py::f"], "reverted": True},
        {"turn": "T6", "kind": "edit", "nodes": ["a.py::g"], "reverted": False},
        {"turn": "T20", "kind": "edit", "nodes": ["b.py::h"], "reverted": False},
    ]
    findings = [{"kind": "claim_not_backed", "functions": ["a.py::g"]}]
    ds = [
        dec("T2", "agent", "choice"),  # nodes from the edit at T3; reverted; but a person redirects at T4 -> overruled wins
        dec("T4", "human", "redirect"),
        dec("T5", "agent", "choice", nodes=["a.py::g", "ghost::id"]),  # model gave nodes: kept as given
        dec("T7", "agent", "choice", rule_followed=False),  # nothing within the window after T7
        dec("T9", "human", "requirement"),
        dec("T30", "human", "permission_denied", quote="rm b.py", proposal="run rm b.py"),
    ]
    hl = [{"kind": "went_wrong", "text": "x", "turn": "T3", "quote": ""}]
    attach_nodes_and_outcomes(ds, hl, timeline, findings, nodes)
    assert [d["outcome"] for d in ds] == ["overruled", "ok", "unverified", "rule_violated", "ok", "ok"]
    assert ds[0]["nodes"] == ["a.py::f"]
    assert ds[1]["nodes"] == ["a.py::g"]  # the edit that followed the human's redirect
    assert ds[2]["nodes"] == ["a.py::g", "ghost::id"]  # given nodes are not rewritten here; verify_decisions cleans them
    assert ds[3]["nodes"] == []
    assert ds[5]["nodes"] == ["b.py::h"]  # the denied command names a changed file
    assert hl[0]["nodes"] == []


def test_reverted_outcome_and_no_timeline():
    nodes = [node("a.py::f", "a.py", "f")]
    d1 = [dec("T1", "agent", "choice")]
    attach_nodes_and_outcomes(d1, [], [{"turn": "T2", "kind": "edit", "nodes": ["a.py::f"], "reverted": True}], [], nodes)
    assert d1[0]["outcome"] == "reverted"
    d2 = [dec("T1", "agent", "choice")]
    attach_nodes_and_outcomes(d2, [], [], [], [])
    assert d2[0]["outcome"] == "ok" and d2[0]["nodes"] == []
