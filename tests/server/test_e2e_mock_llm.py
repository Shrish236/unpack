"""A whole push, end to end, with no Gemini call.

A real git repo, a real Gemini CLI session file, the real CLI payload builder, the real ingest endpoint, the real worker
job and the real API. The only thing replaced is the model: `MockLLMClient` answers from the prompts it is given. If this
passes, plugging in a real key changes the answers and nothing else.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import jsonschema
import pytest
from sqlalchemy import func, select

from cli.hook import build_push_payload
from server.app.config import settings
from server.app.dashboard_seed import seed_dashboard
from server.app.db import session_scope
from server.app.llm import client as llm_client
from server.app.llm.client import LLMBackendError, set_llm_client
from server.app.llm.mock import MOCK_MODEL, MockLLMClient
from server.app.models import (
    Analysis, Decision, FunctionReason, LLMCall, ReviewFinding, Session, SessionSignals, TeamPR,
)
from server.app.pipeline.rollup import rollup_measured

from .conftest import GIT_ENV, Origin
from .helpers import create_repo, gzip_json, ingest_headers
from .conftest import drain_jobs
from .test_ingest_and_analysis import login

REPO_ROOT = Path(__file__).resolve().parents[2]

def _pad(name):  # unchanged lines between the edits, so git reports them as separate hunks
    return "".join(f"# {name} note {i}\n" for i in range(8))


PRICING_V0 = (_pad("head") + '''

def total(items):
    return sum(i.price for i in items)


''' + _pad("mid") + '''

def apply_discount(amount, pct):
    return amount - amount * pct / 100


''' + _pad("tail") + '''

def legacy_round(x):
    return round(x)
''')
PRICING_V1 = PRICING_V0.replace(
    "def apply_discount(amount, pct):\n    return",
    'def apply_discount(amount, pct):\n    if pct < 0 or pct > 100:\n        raise ValueError("pct must be between 0 and 100")\n    return')
PRICING_V2 = ('''import logging

log = logging.getLogger(__name__)
''' + _pad("head") + '''

def total(items):
    return sum(i.price for i in items if i.price is not None)


''' + _pad("mid") + '''

def apply_discount(amount, pct):
    if pct < 0 or pct > 100:
        raise ValueError("pct must be between 0 and 100")
    return amount - amount * pct / 100


''' + _pad("tail") + '''

def format_price(amount):
    return f"{amount:.2f}"
''')
CHECKOUT_V0 = '''from .pricing import total, apply_discount


def checkout(items, pct=0):
    return apply_discount(total(items), pct)
'''
CHECKOUT_V1 = '''from .pricing import total, apply_discount, format_price


def checkout(items, pct=0):
    return format_price(apply_discount(total(items), pct))
'''
TESTS_V0 = '''from shop.pricing import total


def test_total():
    assert total([]) == 0
'''
TESTS_V1 = '''import pytest

from shop.pricing import apply_discount, format_price, total


def test_total():
    assert total([]) == 0


def test_apply_discount_rejects_bad_pct():
    with pytest.raises(ValueError):
        apply_discount(10, 120)


def test_format_price():
    assert format_price(3) == "3.00"
'''
BASE = {"shop/__init__.py": "", "shop/pricing.py": PRICING_V0, "shop/checkout.py": CHECKOUT_V0,
        "tests/test_pricing.py": TESTS_V0, "README.md": "# shop\n"}
HEAD = {"shop/pricing.py": PRICING_V2, "shop/checkout.py": CHECKOUT_V1, "tests/test_pricing.py": TESTS_V1,
        "README.md": "# shop\n\nPrices are rounded to two decimals.\n"}


def _edit(call_id, path, old, new, instruction):
    return {"id": call_id, "name": "replace", "args": {"file_path": path, "instruction": instruction}, "status": "success",
            "resultDisplay": {"originalContent": old, "newContent": new, "fileDiff": "@@ -1 +1 @@"}}


def _shell(call_id, command, result, status="success"):
    return {"id": call_id, "name": "run_shell_command", "args": {"command": command}, "status": status, "result": result}


def session_lines() -> list[dict]:
    """What Gemini CLI writes to disk for this conversation (records are in the order the file has them)."""
    msg = lambda i, t, text, **kw: {"id": f"m{i}", "timestamp": f"2026-11-20T10:{i:02d}:00Z", "type": t, "content": [{"text": text}], **kw}
    return [
        {"sessionId": "e2e12345", "projectHash": "demo", "startTime": "2026-11-20T10:00:00Z", "lastUpdated": "2026-11-20T10:30:00Z"},
        msg(1, "user", "Validate the discount percentage in apply_discount and remove legacy_round, then show prices with two decimals"),
        msg(2, "gemini", "I will validate pct and add a rounding helper. I can add the babel package for formatting.",
            thoughts=[{"subject": "Plan", "description": "Validate pct, drop legacy_round, add format_price"}],
            tokens={"input": 4000, "output": 600, "thoughts": 200, "total": 4800},
            toolCalls=[
                _edit("c1", "shop/pricing.py", PRICING_V0, PRICING_V1, "Reject a discount outside 0 to 100"),
                _shell("c2", "pip install babel", "Tool call cancelled by user", status="cancelled"),
                _shell("c3", "pytest tests", "tests/test_pricing.py F\n1 failed in 0.04s\nExit Code: 1"),
            ]),
        msg(3, "user", "Don't add a new package for formatting, use the standard library instead"),
        msg(4, "gemini", "Understood. I will format with an f-string and update checkout and the tests. Added tests for both new behaviours.",
            tokens={"input": 5200, "output": 900, "thoughts": 100, "total": 6200},
            toolCalls=[
                _edit("c4", "shop/pricing.py", PRICING_V1, PRICING_V2, "Skip None prices, drop legacy_round, add format_price"),
                _edit("c5", "shop/checkout.py", CHECKOUT_V0, CHECKOUT_V1, "Format the checkout total"),
                _edit("c6", "tests/test_pricing.py", TESTS_V0, TESTS_V1, "Cover the new behaviour"),
                _shell("c7", "pytest tests", "3 passed in 0.06s\nExit Code: 0"),
            ]),
        msg(5, "gemini", "Done. All tests pass.", tokens={"input": 6000, "output": 80, "total": 6080}),
    ]


@pytest.fixture
def world(tmp_path):
    origin = Origin(tmp_path, BASE, HEAD)
    subprocess.run(["git", "remote", "add", "origin", "https://github.com/o/r.git"], cwd=origin.work, check=True, env=GIT_ENV)
    session_file = tmp_path / "session-2026-11-20T10-00-e2e12345.jsonl"
    session_file.write_text("\n".join(json.dumps(r) for r in session_lines()) + "\n", encoding="utf-8")
    return origin, session_file


def cli_payload(origin: Origin, session_file: Path) -> dict:
    """The payload the real pre-push hook would send, built by the real CLI code from the real repo."""
    payload, picked = build_push_payload(
        origin.work, branch="feature/discounts", base_sha=origin.base_sha, head_sha=origin.head_sha,
        default_branch_override="main", session_path=session_file, agent="gemini-cli",
    )
    assert picked == session_file
    return payload


@pytest.fixture
def mock_llm(monkeypatch):
    monkeypatch.setattr(settings, "REASONING_ENABLED", True)
    monkeypatch.setattr(settings, "GEMINI_BACKEND", "mock")
    monkeypatch.setattr(llm_client, "_mock_client", None)
    set_llm_client(None)
    yield
    monkeypatch.setattr(llm_client, "_mock_client", None)


async def run_push(client, origin, session_file, token):
    payload = cli_payload(origin, session_file)
    resp = await client.post("/v1/ingest", content=gzip_json(payload), headers=ingest_headers(token))
    assert resp.status_code == 202, resp.text
    public_id = resp.json()["analysis"]["public_id"]
    assert await drain_jobs() >= 1
    await login(client)
    return public_id, payload


async def test_cli_payload_carries_everything_the_server_needs(world):
    origin, session_file = world
    p = cli_payload(origin, session_file)
    assert p["session"]["agent"] == "gemini-cli" and len(p["session"]["lines"]) == 6
    assert p["session"]["lines"][2]["tokens"] == {"input": 4000, "output": 600, "thoughts": 200, "total": 4800}
    paths = {f["path"]: f for f in p["changed_files"]}
    assert set(paths) == {"shop/pricing.py", "shop/checkout.py", "tests/test_pricing.py", "README.md"}
    assert paths["shop/pricing.py"]["head_content"] == PRICING_V2 and paths["README.md"]["status"] == "M"
    assert "@@" in p["diff"] and len(p["commits"]) >= 1


async def test_full_push_with_mock_llm(client, tmp_data_dir, world, mock_llm, fake_github):
    origin, session_file = world
    _, token = await create_repo(remote_url=origin.remote_url)
    public_id, payload = await run_push(client, origin, session_file, token)

    res = await client.get(f"/api/analyses/{public_id}")
    assert res.status_code == 200, res.text
    body = res.json()

    # ---- 1. the response honours the published contract, including every new field
    schema = json.loads((REPO_ROOT / "contract" / "schema" / "analysis_response.json").read_text(encoding="utf-8"))
    jsonschema.validate(instance=body, schema=schema)

    a = body["analysis"]
    assert a["status"] == "done" and a["llm_model"] == MOCK_MODEL and a["agent"] == "gemini-cli" and a["prompt_version"] == settings.PROMPT_VERSION
    assert body["banner"] is None, body["banner"]

    # ---- 2. the graph: every changed function, deleted ghost, container, and a reason on each live one
    nodes = {n["id"]: n for n in body["graph"]["nodes"]}
    kinds = {i.split("::")[1]: n["change"]["kind"] for i, n in nodes.items() if n["layer"] == "changed" and "::" in i and n["change"]}
    assert kinds["apply_discount"] in ("functional", "signature")
    assert kinds["format_price"] == "added" and kinds["total"] == "functional"
    assert nodes["shop/pricing.py::legacy_round"]["layer"] == "ghost"
    assert nodes["shop/pricing.py"]["kind"] == "file" and nodes["shop/checkout.py::checkout"]["layer"] == "changed"
    for nid in ("shop/pricing.py::apply_discount", "shop/pricing.py::total", "shop/pricing.py::format_price", "shop/checkout.py::checkout"):
        assert nodes[nid]["has_reason"] is True, nid
        r = body["reasons"][nid]
        assert r["driver"] == "user_asked" and r["evidence"] and r["reason"].startswith("Mock:")
    assert body["stats"]["functions_changed"] >= 5 and body["stats"]["by_source"]["session"] >= 4

    # ---- 3. both flows list every changed function exactly once
    flow = body["flow"]
    det, ai = flow["deterministic"], flow["llm"]
    assert ai["mode"] == "llm" and flow["model"] == MOCK_MODEL and ai["stages"] and det["stages"]
    assert sorted(det["order"]) == sorted(ai["order"]) and len(set(det["order"])) == len(det["order"])
    live = {i for i, n in nodes.items() if n["layer"] in ("changed", "ghost") and n["kind"] in ("function", "method")}
    assert set(det["order"]) == live
    checkout_stage = next(s for s in det["stages"] if "shop/checkout.py::checkout" in s["node_ids"])
    assert len(checkout_stage["node_ids"]) >= 2  # checkout calls apply_discount and total: one call chain
    assert det["order"].index("shop/checkout.py::checkout") < det["order"].index("shop/pricing.py::apply_discount")  # callers first
    assert det["order"][-1] == "shop/pricing.py::legacy_round"  # deleted code last

    # ---- 4. the file diff keeps every hunk and names an owner for each
    files = {f["path"]: f for f in body["diff_files"]}
    assert set(files) == {"shop/pricing.py", "shop/checkout.py", "tests/test_pricing.py", "README.md"}
    owners = {(h["owner_kind"], tuple(h["owners"])) for h in files["shop/pricing.py"]["hunks"]}
    assert ("module", ("shop/pricing.py",)) in owners  # the new import and logger
    assert any(k == "function" and "shop/pricing.py::legacy_round" in o for k, o in owners)  # removed lines, old-side match
    assert any(k == "function" and "shop/pricing.py::apply_discount" in o for k, o in owners)
    assert files["README.md"]["hunks"][0]["owner_kind"] == "file" and files["README.md"]["hunks"][0]["owners"] == []
    assert files["shop/pricing.py"]["added"] > 0 and files["shop/pricing.py"]["removed"] > 0
    total_hunks = sum(len(f["hunks"]) for f in files.values())
    assert total_hunks >= 6
    for nid, hunks in body["diff_hunks"].items():  # the per-function view points at the same hunks
        for h in hunks:
            assert any(fh["id"] == h["id"] and nid in fh["owners"] for f in files.values() for fh in f["hunks"])

    # ---- 5. governance: decisions with nodes and outcomes, a refused tool call, signals
    gov = body["governance"]
    assert gov["available"] and gov["attempts"] == 2  # a failing test run, then another edit
    by_kind = {d["kind"]: d for d in gov["decisions"]}
    assert "permission_denied" in by_kind and by_kind["permission_denied"]["source"] == "parsed"
    human = [d for d in gov["decisions"] if d["actor"] == "human" and d["kind"] != "permission_denied"]
    assert human and human[0]["kind"] == "reject" and human[0]["type"] == "dependency" and human[0]["statement"]
    agent = [d for d in gov["decisions"] if d["actor"] == "agent"]
    assert agent and agent[0]["outcome"] == "overruled"  # the person rejected it on the next turn
    assert all(n in nodes for d in gov["decisions"] for n in d["nodes"])
    assert human[0]["nodes"] and agent[0]["nodes"]  # the model was shown the ids in ## CHANGED CODE and used them
    assert gov["tool_stats"]["replace"]["calls"] == 4 and gov["tool_stats"]["replace"]["tokens"] > 0
    assert gov["highlights"] and gov["highlights"][0]["kind"] == "went_right"
    assert gov["human_interventions"] >= 2

    # ---- 6. the timeline and facts come from the session, not the model
    kinds_t = [t["kind"] for t in body["timeline"]]
    assert kinds_t.count("user_request") == 2 and "denied" in kinds_t and "test_run" in kinds_t
    assert body["facts"]["tested_after_final_edit"] is True and body["facts"]["last_test_run"]["exit_code"] == 0

    # ---- 7. the prompts the model would have received
    mock = llm_client.get_llm_client()
    assert isinstance(mock, MockLLMClient)
    by_schema = {r["schema"]: r for r in mock.requests}
    assert [r["schema"] for r in mock.requests] == ["LLMReasoningOutput", "LLMFlowOutput", "LLMDecisionOutput"]
    for needed in ("## TASK", "## CHANGED FUNCTIONS", "## CODE CONTEXT", "## FACTS", "## SESSION"):
        assert needed in by_schema["LLMReasoningOutput"]["user"], needed
    for needed in ("## TASK", "## CHANGED FUNCTIONS", "## DEFAULT ORDER"):
        assert needed in by_schema["LLMFlowOutput"]["user"], needed
    for needed in ("## TASK", "## STEERING", "## REFUSED TOOL CALLS", "## CHANGED CODE", "## SIGNALS", "## SESSION"):
        assert needed in by_schema["LLMDecisionOutput"]["user"], needed
    assert "pip install babel" in by_schema["LLMDecisionOutput"]["user"]
    for r in mock.requests:  # every section the model is sent is explained to it, and the format reminder comes last
        headings = re.findall(r"^## ([A-Z][A-Z ]+?)(?: \(|$)", r["user"], re.M)
        assert headings and headings[-1] == "RESPONSE", (r["schema"], headings)
        for h in headings:
            assert f"`## {h}`" in r["system"], f"{r['schema']}: the system prompt never explains ## {h}"
        assert "exactly one JSON object" in r["system"] and "JSON Schema of the answer" in r["system"]
    assert "F1, F2" in by_schema["LLMReasoningOutput"]["user"].split("## RESPONSE")[1]  # the labels it must answer
    assert "S1" in by_schema["LLMDecisionOutput"]["user"].split("## RESPONSE")[1] or "(use null" in by_schema["LLMDecisionOutput"]["user"]
    assert "shop/pricing.py::apply_discount" in by_schema["LLMDecisionOutput"]["user"].split("## RESPONSE")[1]  # node ids it may use
    if dump := os.environ.get("UNPACK_DUMP_PROMPTS"):  # a way to read exactly what the model is sent
        for r in mock.requests:
            text = "=== SYSTEM ===\n" + r["system"] + "\n\n=== USER ===\n" + r["user"] + "\n"
            Path(dump, f"{r['schema']}.txt").write_text(text, encoding="utf-8")

    # ---- 8. everything is in the database
    async with session_scope() as db:
        row = (await db.execute(select(Analysis).where(Analysis.public_id == public_id))).scalar_one()
        assert row.flow["llm"] and row.diff_files and row.prompt_version == settings.PROMPT_VERSION
        reasons = (await db.execute(select(FunctionReason).where(FunctionReason.analysis_id == row.id))).scalars().all()
        assert len(reasons) >= 4 and all(r.rejected is None for r in reasons)
        decisions = (await db.execute(select(Decision).where(Decision.analysis_id == row.id))).scalars().all()
        assert {d.outcome for d in decisions} >= {"overruled", "ok"} and any(d.node_ids for d in decisions)
        sig = await db.get(SessionSignals, row.id)
        assert sig.signals["attempts"] == 2 and sig.signals["session_key"] and sig.steering is not None
        calls = (await db.execute(select(LLMCall).where(LLMCall.analysis_id == row.id))).scalars().all()
        assert sorted(c.purpose for c in calls) == ["decisions", "flow", "reasons"]
        assert all(c.model == MOCK_MODEL and c.status == "ok" and c.input_tokens > 0 and c.output_tokens > 0 for c in calls)
        sess = (await db.execute(select(Session))).scalar_one()
        assert len(sess.turns) >= 8 and sess.agent == "gemini-cli"
        assert (await db.execute(select(func.count()).select_from(ReviewFinding))).scalar_one() >= 0

    # ---- 9. turns endpoint serves the turns the evidence cites
    ev_turns = sorted({e["turn"] for r in body["reasons"].values() for e in r["evidence"]})
    turns = (await client.get(f"/api/analyses/{public_id}/turns?ids={','.join(ev_turns)}")).json()["turns"]
    assert turns and turns[0]["kind"] == "user"

    # ---- 10. sending the same push again changes nothing and costs nothing
    again = await client.post("/v1/ingest", content=gzip_json(payload), headers=ingest_headers(token))
    assert again.status_code == 200 and again.json()["deduplicated"] is True
    assert await drain_jobs() == 0
    async with session_scope() as db:
        assert (await db.execute(select(func.count()).select_from(LLMCall))).scalar_one() == 3


async def test_dashboards_pick_up_the_measured_push(client, tmp_data_dir, world, mock_llm, fake_github, monkeypatch):
    monkeypatch.setattr(settings, "DEV_VIEWER_LOGIN", "dev")
    async with session_scope() as db:
        await seed_dashboard(db)
    origin, session_file = world
    _, token = await create_repo(remote_url=origin.remote_url)
    public_id, _ = await run_push(client, origin, session_file, token)

    exec_ = (await client.get("/api/dashboard/exec?period=30d")).json()
    assert exec_["sources"]["trend"] == "measured" and exec_["kpis"]["sessions"] == 1
    assert exec_["measured"]["sessions"] == 1 and exec_["measured"]["human_decisions"] >= 2
    assert exec_["rework"] == {"first": 0, "missed": 1, "thin": 0}  # a rejection and two attempts: the agent missed it
    assert exec_["agents"][0]["name"] == MOCK_MODEL and exec_["agents"][0]["tool"] == "Gemini CLI"
    assert sum(exec_["mix"]["dependency"]) >= 1
    team = (await client.get("/api/dashboard/teams/payments")).json()
    pr = next(p for p in team["prs"] if p["source"] == "measured")
    assert pr["public_id"] == public_id and pr["human_decisions"] >= 2 and pr["attempts"] == 2
    assert team["funnel"]["total"] == 1 and team["sources"]["funnel"] == "measured"
    # the PR link the page builds really resolves to this analysis
    assert (await client.get(f"/api/analyses/{pr['public_id']}")).json()["analysis"]["public_id"] == public_id


async def test_quota_exhausted_still_renders_a_complete_analysis(client, tmp_data_dir, world, fake_github, monkeypatch):
    class Quota:
        calls = 0

        async def generate_json(self, **kw):
            Quota.calls += 1
            raise LLMBackendError("429 RESOURCE_EXHAUSTED: You exceeded your current quota")

    monkeypatch.setattr(settings, "REASONING_ENABLED", True)
    set_llm_client(Quota())
    try:
        origin, session_file = world
        _, token = await create_repo(remote_url=origin.remote_url)
        public_id, _ = await run_push(client, origin, session_file, token)
        body = (await client.get(f"/api/analyses/{public_id}")).json()
    finally:
        set_llm_client(None)
    schema = json.loads((REPO_ROOT / "contract" / "schema" / "analysis_response.json").read_text(encoding="utf-8"))
    jsonschema.validate(instance=body, schema=schema)
    models = 1 + len([m for m in settings.GEMINI_MODEL_FALLBACK.split(",") if m.strip()])
    assert Quota.calls == models  # the reasons call tried each model once; the flow and decision calls never went out
    assert body["analysis"]["status"] == "done" and body["banner"]["kind"] == "reasons_unavailable" and "quota" in body["banner"]["message"]
    assert body["flow"]["llm"] is None and body["flow"]["deterministic"]["order"]
    assert body["reasons"] and all(r["reason"].startswith("Not analysed") for r in body["reasons"].values())
    assert not any(n["has_reason"] for n in body["graph"]["nodes"])
    assert body["diff_files"] and body["timeline"]  # everything that needs no model is still there
    gov = body["governance"]
    assert gov["available"] and [d["kind"] for d in gov["decisions"]] == ["permission_denied"] and gov["attempts"] == 2


async def test_late_session_reanalyses_the_same_push(client, tmp_data_dir, world, mock_llm, fake_github):
    origin, session_file = world
    _, token = await create_repo(remote_url=origin.remote_url)
    bare = cli_payload(origin, session_file)
    bare["session"] = None
    first = await client.post("/v1/ingest", content=gzip_json(bare), headers=ingest_headers(token))
    public_id = first.json()["analysis"]["public_id"]
    await drain_jobs()
    await login(client)
    assert (await client.get(f"/api/analyses/{public_id}")).json()["banner"]["kind"] == "no_session"

    second = await client.post("/v1/ingest", content=gzip_json(cli_payload(origin, session_file)), headers=ingest_headers(token))
    assert second.status_code == 202 and second.json()["deduplicated"] is False
    assert second.json()["analysis"]["public_id"] == public_id  # same URL
    await drain_jobs()
    body = (await client.get(f"/api/analyses/{public_id}")).json()
    assert body["banner"] is None and body["governance"]["available"] and body["flow"]["llm"]
    async with session_scope() as db:
        assert (await db.execute(select(func.count()).select_from(Decision))).scalar_one() >= 3
