"""What every session must yield: real agy edit shapes, tokens, session identity, graph context for the LLM."""

from __future__ import annotations

import json
import secrets
from pathlib import Path

import pytest

from server.app.config import settings
from server.app.db import session_scope
from server.app.llm import client as llm_client
from server.app.llm.graph_context import GraphTools, build_code_context
from server.app.llm.graph_notes import graph_notes
from server.app.models import Analysis, Push, Repo, SessionSignals
from server.app.pipeline.agy_session import AGY_AGENT, parse_agy_transcript, reconstruct_edit_states
from server.app.pipeline.rollup import _load
from server.app.pipeline.session import normalize_repo_path
from server.app.pipeline.signals import compute_signals, session_key
from tests.helpers import build

BASE_CART = (
    '"""A shopping cart."""\n'
    "class Cart:\n"
    "    def subtotal(self) -> float:\n"
    "        return 0.0\n"
)


def _agy(lines: list[dict]) -> dict:
    return {"agent": AGY_AGENT, "file_name": "transcript_full.jsonl", "lines": lines}


# The shapes below were captured from real Antigravity CLI sessions: edit_file(Path, Target, Replacement),
# read_file(Path), and an absolute Windows path.
REAL_EDIT = [
    {"type": "USER_INPUT", "created_at": "2026-11-20T10:00:00Z", "content": "<USER_REQUEST>add total_items</USER_REQUEST>"},
    {"type": "PLANNER_RESPONSE", "created_at": "2026-11-20T10:00:01Z", "input_tokens": 400, "output_tokens": 20, "tool_calls": [
        {"name": "read_file", "args": {"Path": "C:\\Users\\dev\\proj\\shop\\cart.py"}},
        {"name": "edit_file", "args": {
            "Path": "C:\\Users\\dev\\proj\\shop\\cart.py",
            "Target": "    def subtotal(self) -> float:",
            "Replacement": "    def total_items(self) -> int:\n        return 0\n\n    def subtotal(self) -> float:",
        }},
    ]},
    {"type": "GENERIC", "status": "DONE", "content": "Showing lines 1-4 of 4"},
    {"type": "GENERIC", "status": "DONE", "content": "Made 1 replacement (+3/-0 lines)."},
]


def test_real_agy_edit_file_and_read_file_become_turns_with_repo_relative_paths():
    session = parse_agy_transcript(_agy(REAL_EDIT), known_paths={"shop/cart.py"})
    kinds = [(t.kind, t.path, t.tool_name) for t in session.turns]
    assert ("read", "shop/cart.py", "read_file") in kinds
    assert ("edit", "shop/cart.py", "edit_file") in kinds
    edit = next(t for t in session.turns if t.kind == "edit")
    assert edit.status == "DONE" and edit.file_diff and "+    def total_items" in edit.file_diff
    assert edit.tokens == 210  # (400 + 20) split over the message's two tool calls


def test_windows_absolute_paths_map_to_known_repo_paths():
    assert normalize_repo_path("C:\\Users\\dev\\proj\\shop\\cart.py", [], {"shop/cart.py"}) == "shop/cart.py"


def test_snippet_edits_are_replayed_over_the_base_file_for_the_linker():
    session = parse_agy_transcript(_agy(REAL_EDIT), known_paths={"shop/cart.py"})
    assert reconstruct_edit_states(session, {"shop/cart.py": BASE_CART}) == 1
    edit = next(t for t in session.turns if t.kind == "edit")
    assert edit.original_content == BASE_CART
    assert "def total_items" in edit.new_content and "def subtotal" in edit.new_content


def test_a_snippet_whose_target_is_not_in_the_file_is_left_unlinked():
    lines = json.loads(json.dumps(REAL_EDIT))
    lines[1]["tool_calls"][1]["args"]["Target"] = "    def nothing_like_this(self):"
    session = parse_agy_transcript(_agy(lines), known_paths={"shop/cart.py"})
    assert reconstruct_edit_states(session, {"shop/cart.py": BASE_CART}) == 0
    assert next(t for t in session.turns if t.kind == "edit").new_content is None


def test_a_failed_edit_is_not_replayed():
    lines = json.loads(json.dumps(REAL_EDIT))
    lines[3]["status"] = "ERROR"
    session = parse_agy_transcript(_agy(lines), known_paths={"shop/cart.py"})
    assert reconstruct_edit_states(session, {"shop/cart.py": BASE_CART}) == 0


def test_session_key_is_stable_across_pushes_and_differs_between_conversations():
    a1 = parse_agy_transcript(_agy(REAL_EDIT))
    a2 = parse_agy_transcript(_agy(REAL_EDIT + [{"type": "USER_INPUT", "content": "<USER_REQUEST>more</USER_REQUEST>"}]))
    other = json.loads(json.dumps(REAL_EDIT))
    other[0]["content"] = "<USER_REQUEST>a different task</USER_REQUEST>"
    b = parse_agy_transcript(_agy(other))
    assert session_key(a1) == session_key(a2) != session_key(b)
    assert compute_signals(a1)["session_key"] == session_key(a1)


async def test_a_conversation_pushed_twice_counts_once_in_the_rollup(db_ready):
    async with session_scope() as db:
        repo = Repo(owner="o", name="r", remote_url="https://github.com/o/r.git", default_branch="main",
                    ingest_token_hash="h", status="active")
        db.add(repo)
        await db.flush()
        for _ in range(2):  # the same conversation, two pushes
            push = Push(repo_id=repo.id, branch="b", base_sha="a" * 40, head_sha=secrets.token_hex(20),
                        has_session=True, session_agent=AGY_AGENT)
            db.add(push)
            await db.flush()
            a = Analysis(push_id=push.id, public_id=secrets.token_hex(8), status="done")
            db.add(a)
            await db.flush()
            db.add(SessionSignals(analysis_id=a.id, signals={"session_key": "same"}, highlights=[], steering={}))
    async with session_scope() as db:
        assert len(await _load(db)) == 1


def test_graph_context_lists_callers_callees_and_test_reach():
    g = build("flow")
    some = next(fid for fid, f in g.funcs.items() if not f.is_test and g.in_adj.get(fid))
    text = build_code_context(g, [some], {some: "F1"})
    assert text.startswith("## CODE CONTEXT") and "F1 " in text and "callers (" in text and "calls (" in text


def test_graph_tools_resolve_names_and_never_raise():
    g = build("flow")
    tools = GraphTools(g, lambda path: "line one\n" * 400)
    fid = next(iter(g.funcs))
    assert fid in tools.find_function(g.funcs[fid].name)
    assert "Unknown function" in tools.get_callers("does_not_exist")
    assert "line one" in tools.get_source(fid)
    assert tools.calls and len(tools.as_tools()) == 5


class ToolClient:
    def __init__(self) -> None:
        self.seen = None

    async def generate_text_with_tools(self, **kw):
        self.seen = kw
        return llm_client.RawLLMResponse(text="- send is called by 3 functions", model="fake", input_tokens=10, output_tokens=5)


async def test_graph_notes_are_off_by_default_and_used_when_enabled(monkeypatch):
    tools = GraphTools(build("flow"), lambda p: None)
    client = ToolClient()
    monkeypatch.setattr(settings, "LLM_GRAPH_TOOLS", False)
    assert await graph_notes(tools, changed=["m.py::x"], task="t", client=client) == (None, [])
    monkeypatch.setattr(settings, "LLM_GRAPH_TOOLS", True)
    notes, calls = await graph_notes(tools, changed=["m.py::x"], task="t", client=client)
    assert notes == "- send is called by 3 functions" and calls[0].purpose == "graph_notes"
    assert len(client.seen["tools"]) == 5


def test_prompts_v2_tell_the_model_the_graph_is_not_evidence():
    root = Path(__file__).resolve().parents[2] / "server" / "app" / "llm" / "prompts"
    assert "Never put them in `evidence`" in (root / "reasons_v2.md").read_text(encoding="utf-8")
    assert "context only" in (root / "decisions_v2.md").read_text(encoding="utf-8")
