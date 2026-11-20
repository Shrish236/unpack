"""Signals, decision extraction and the measured rollup. The LLM is replaced by a fake client."""

from __future__ import annotations

import json
import secrets

import pytest
from sqlalchemy import select

from server.app.config import settings
from server.app.dashboard_seed import seed_dashboard
from server.app.db import session_scope
from server.app.llm import client as llm_client
from server.app.models import (
    Analysis, Decision, GovCandidate, GovEvidence, GovSkillRule, Push, Repo, SessionSignals, TeamPR,
)
from server.app.pipeline.agy_session import AGY_AGENT, parse_agy_transcript
from server.app.pipeline.decisions import denied_decisions, extract_decisions
from server.app.pipeline.rollup import cluster, measured_summary, rollup_measured
from server.app.pipeline.session import is_denied, parse_gemini_session
from server.app.pipeline.signals import compute_signals
from server.app.pipeline.steering import SteeringSnapshot, parse_rules


def _gemini(messages: list[dict]) -> dict:
    return {"agent": "gemini-cli", "file_name": "s.jsonl", "lines": [
        {"$set": {"sessionId": "s1", "startTime": "2026-11-20T10:00:00Z", "directories": []}},
        *messages,
    ]}


def _agy(lines: list[dict]) -> dict:
    return {"agent": AGY_AGENT, "file_name": "transcript_full.jsonl", "lines": lines}


def test_is_denied_reads_status_and_result_text():
    assert is_denied("cancelled")
    assert is_denied("success", "Tool call rejected by user")
    assert not is_denied("success", "installed fine")
    assert not is_denied(None)


def test_agy_denied_command_and_tokens_are_captured():
    session = parse_agy_transcript(_agy([
        {"type": "USER_INPUT", "content": "<USER_REQUEST>add retries</USER_REQUEST>", "created_at": "t"},
        {"type": "PLANNER_RESPONSE", "created_at": "t", "input_tokens": 100, "output_tokens": 20,
         "tool_calls": [{"name": "run_command", "args": {"CommandLine": "pip install tenacity"}}]},
        {"type": "GENERIC", "status": "CANCELED", "content": "The user rejected this command."},
    ]))
    sig = compute_signals(session)
    assert [d["target"] for d in sig["denied"]] == ["pip install tenacity"]
    assert sig["tool_stats"]["run_command"] == {"calls": 1, "tokens": 120}
    dec = denied_decisions(sig)
    assert dec[0]["kind"] == "permission_denied" and dec[0]["type"] == "dependency"


def test_gemini_cancelled_tool_is_a_denial_and_tokens_split_per_call():
    session = parse_gemini_session(_gemini([
        {"id": "m1", "type": "user", "content": [{"text": "add retries"}], "timestamp": "t"},
        {"id": "m2", "type": "gemini", "content": "", "timestamp": "t", "tokens": {"total": 300}, "toolCalls": [
            {"name": "run_shell_command", "args": {"command": "npm install lodash"}, "status": "cancelled", "result": []},
            {"name": "read_file", "args": {"file_path": "a.py"}, "status": "success", "result": []},
        ]},
    ]))
    sig = compute_signals(session)
    assert [d["turn"] for d in sig["denied"]] == ["T2"]
    assert sig["tool_stats"]["read_file"]["tokens"] == 150


def test_flags_find_new_dependency_and_skipped_test():
    session = parse_agy_transcript(_agy([{"type": "USER_INPUT", "content": "<USER_REQUEST>x</USER_REQUEST>"}]))
    diff = (
        "--- a/requirements.txt\n+++ b/requirements.txt\n@@ -1 +1,2 @@\n httpx==0.27\n+tenacity==8.2.3\n"
        "--- a/tests/test_a.py\n+++ b/tests/test_a.py\n@@ -1 +1,2 @@\n+@pytest.mark.skip\n+def test_a(): pass\n"
    )
    flags = {f["flag"] for f in compute_signals(session, diff)["flags"]}
    assert flags == {"new-dependency", "skipped-test"}


def test_attempts_count_failed_test_runs_followed_by_an_edit():
    session = parse_agy_transcript(_agy([
        {"type": "USER_INPUT", "content": "<USER_REQUEST>x</USER_REQUEST>"},
        {"type": "PLANNER_RESPONSE", "tool_calls": [{"name": "run_command", "args": {"CommandLine": "pytest -q"}}]},
        {"type": "GENERIC", "content": "Command exited with code 1.\nCommand output:\n1 failed"},
        {"type": "PLANNER_RESPONSE", "tool_calls": [{"name": "write_to_file", "args": {"TargetFile": "a.py"}}]},
        {"type": "GENERIC", "content": "ok"},
    ]))
    assert compute_signals(session)["attempts"] == 2


def test_parse_rules_takes_bullets_under_headings_and_skips_code():
    rules = parse_rules("GEMINI.md", "# Deps\n- Never add a runtime dependency without approval\nprose line\n```\n- not a rule at all here\n```\n1. Retries use exponential backoff, five at most\n- short\n")
    assert [r.text for r in rules] == [
        "Never add a runtime dependency without approval", "Retries use exponential backoff, five at most",
    ]
    assert rules[0].section == "Deps" and rules[0].id == "S1"


def test_cluster_groups_the_same_correction_worded_differently():
    items = [
        {"statement": "Do not add a new runtime dependency for small helpers", "type": "dependency"},
        {"statement": "Don't add runtime dependencies for helpers", "type": "dependency"},
        {"statement": "Never skip a failing test", "type": "test"},
    ]
    groups = cluster(items)
    assert sorted(len(g) for g in groups) == [1, 2]


class FakeLLM:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    async def generate_json(self, **kwargs):
        return llm_client.RawLLMResponse(text=json.dumps(self.payload), model="fake")


@pytest.fixture
def fake_llm(monkeypatch):
    monkeypatch.setattr(settings, "REASONING_ENABLED", True)
    yield lambda payload: llm_client.set_llm_client(FakeLLM(payload))
    llm_client.set_llm_client(None)


async def test_extract_keeps_verified_decisions_and_drops_invented_quotes(fake_llm):
    session = parse_agy_transcript(_agy([
        {"type": "USER_INPUT", "content": "<USER_REQUEST>add retries</USER_REQUEST>"},
        {"type": "PLANNER_RESPONSE", "content": "I will add tenacity"},
        {"type": "USER_INPUT", "content": "<USER_REQUEST>no, don't add tenacity</USER_REQUEST>"},
    ]))
    steering = SteeringSnapshot(files={}, rules=parse_rules("GEMINI.md", "- Never add a runtime dependency without approval\n"))
    fake_llm({
        "decisions": [
            {"turn": "T3", "actor": "human", "kind": "reject", "type": "dependency", "proposal": "p", "choice": "c",
             "statement": "Do not add a runtime dependency", "quote": "don't add tenacity", "rule_id": "S1", "rule_followed": False},
            {"turn": "T3", "actor": "human", "kind": "reject", "type": "dependency", "quote": "this was never said"},
            {"turn": "T2", "actor": "human", "kind": "reject", "type": "dependency", "quote": "I will add tenacity"},
            {"turn": "T3", "actor": "human", "kind": "reject", "type": "dependency", "quote": "don't add tenacity", "rule_id": "S99"},
        ],
        "highlights": [{"kind": "went_wrong", "text": "Planned an unapproved dependency", "turn": "T2", "quote": "I will add tenacity"}],
    })
    res = await extract_decisions(session, steering, compute_signals(session))
    assert [(d["turn"], d["rule_id"], d["rule_followed"]) for d in res.decisions] == [("T3", "S1", False), ("T3", None, None)]
    assert res.rejected_count == 2  # the invented quote, and the "human" decision on an assistant turn
    assert res.highlights[0]["kind"] == "went_wrong"


async def test_extract_without_reasoning_still_returns_parsed_denials(monkeypatch):
    monkeypatch.setattr(settings, "REASONING_ENABLED", False)
    session = parse_agy_transcript(_agy([
        {"type": "PLANNER_RESPONSE", "tool_calls": [{"name": "run_command", "args": {"CommandLine": "pip install x"}}]},
        {"type": "GENERIC", "status": "REJECTED", "content": ""},
    ]))
    res = await extract_decisions(session, SteeringSnapshot({}, []), compute_signals(session))
    assert [d["kind"] for d in res.decisions] == ["permission_denied"]


async def _add_session(repo_id: int, branch: str, decisions: list[dict], rule_text: str | None = None) -> None:
    async with session_scope() as db:
        push = Push(repo_id=repo_id, branch=branch, base_sha="a" * 40, head_sha=secrets.token_hex(20),
                    has_session=True, session_agent="antigravity-cli")
        db.add(push)
        await db.flush()
        a = Analysis(push_id=push.id, public_id=secrets.token_hex(8), status="done", summary="Add retries")
        db.add(a)
        await db.flush()
        for d in decisions:
            db.add(Decision(analysis_id=a.id, turn=d["turn"], actor=d.get("actor", "human"), kind=d["kind"],
                            type=d["type"], proposal="p", choice="c", statement=d.get("statement", ""),
                            quote=d["quote"], rule_id=d.get("rule_id"), rule_followed=d.get("rule_followed")))
        rules = [{"id": "S1", "text": rule_text, "source": "GEMINI.md", "section": "Deps"}] if rule_text else []
        db.add(SessionSignals(analysis_id=a.id, signals={"agent": "antigravity-cli", "attempts": 2,
                                                         "tool_stats": {"run_command": {"calls": 3, "tokens": 900}},
                                                         "flags": [{"flag": "new-dependency", "path": "r.txt", "detail": "x"}]},
                              highlights=[], steering={"rules": rules}))


async def test_rollup_builds_candidates_rules_and_pr_rows_and_is_idempotent(db_ready):
    async with session_scope() as db:
        await seed_dashboard(db)
        repo = Repo(owner="o", name="r", remote_url="https://github.com/o/r.git", default_branch="main",
                    ingest_token_hash="h", status="active")
        db.add(repo)
        await db.flush()
        repo_id = repo.id
    dep = {"turn": 3, "kind": "reject", "type": "dependency", "quote": "no tenacity",
           "statement": "Do not add a runtime dependency for small helpers", "rule_id": "S1", "rule_followed": False}
    await _add_session(repo_id, "feature/a", [dep], "Never add a runtime dependency without approval")
    await _add_session(repo_id, "feature/b", [{**dep, "quote": "no httpx-retries",
                                               "statement": "Don't add runtime dependencies for helpers"},
                                              {"turn": 5, "actor": "agent", "kind": "choice", "type": "retries",
                                               "quote": "backoff", "rule_id": "S1", "rule_followed": True}],
                       "Never add a runtime dependency without approval")

    for _ in range(2):  # a second run must give the same rows
        summary = await rollup_measured()
        assert summary == {"sessions": 2, "candidates": 1, "rules": 1}

    async with session_scope() as db:
        cands = (await db.execute(select(GovCandidate).where(GovCandidate.source == "measured"))).scalars().all()
        assert len(cands) == 1 and cands[0].sessions == 2 and cands[0].type == "dependency" and cands[0].status == "open"
        evidence = (await db.execute(select(GovEvidence).where(GovEvidence.candidate_id == cands[0].id))).scalars().all()
        assert {e.quote for e in evidence} == {"no tenacity", "no httpx-retries"}
        rule = (await db.execute(select(GovSkillRule).where(GovSkillRule.source == "measured"))).scalars().one()
        assert (rule.followed, rule.violated, rule.skill) == (1, 2, "GEMINI.md")
        prs = (await db.execute(select(TeamPR).where(TeamPR.source == "measured"))).scalars().all()
        assert len(prs) == 2 and all(p.flags == ["new-dependency"] and p.attempts == 2 for p in prs)
        assert (await db.execute(select(GovCandidate).where(GovCandidate.source == "sample"))).scalars().first() is not None
        summary = await measured_summary(db)
    assert summary["sessions"] == 2 and summary["human_decisions"] == 2 and summary["tokens"] == 1800
    assert summary["adherence"] == 33 and summary["flags"] == {"new-dependency": 2}


def test_agy_real_denial_format_is_an_error_step_with_a_user_denied_message():
    session = parse_agy_transcript(_agy([
        {"type": "USER_INPUT", "content": "<USER_REQUEST>find the repo</USER_REQUEST>"},
        {"type": "PLANNER_RESPONSE", "tool_calls": [{"name": "run_command", "args": {"CommandLine": "Get-ChildItem /tmp"}}]},
        {"type": "GENERIC", "status": "ERROR", "content": "Encountered error in step execution",
         "error": "permission check failed: user denied permission to run command: Get-ChildItem /tmp"},
    ]))
    assert session.turns[-1].denied and session.turns[-1].status == "ERROR"
