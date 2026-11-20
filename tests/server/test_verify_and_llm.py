"""Tests for LLM prompt builder, Gemini client fallback/repair/budget, and deterministic verifier."""

from __future__ import annotations

import json
import pytest

from server.app.config import settings
from server.app.llm.client import (
    LLMBackendError,
    LLMEvidenceQuote,
    LLMFunctionReason,
    LLMHistoryStep,
    LLMReasoningOutput,
    LLMReviewFinding,
    RawLLMResponse,
    run_reasoning_llm,
)
from server.app.llm.prompt_builder import build_reasoning_prompt, trim_shell_output
from server.app.pipeline.edit_linker import FunctionLink, LinkOutcome, TestRunFact
from server.app.pipeline.session import UnpackSession, UnpackTurn
from server.app.pipeline.verify import NO_REASON_TEXT, TEXT_ONLY_REASON, verify_reasoning_output


class _ScriptedLLM:
    def __init__(self, responses: list[RawLLMResponse | Exception]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def generate_json(self, **kwargs) -> RawLLMResponse:
        self.calls.append(kwargs)
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _make_sample_session() -> tuple[UnpackSession, LinkOutcome, list[dict]]:
    turns = [
        UnpackTurn(turn_id="T1", kind="user", ts="2026-11-20T10:00:00Z", text="Add retries to sync and async clients."),
        UnpackTurn(
            turn_id="T2",
            kind="edit",
            ts="2026-11-20T10:01:00Z",
            path="httpx/_client.py",
            instruction="Wrap _send_single_request with retry loop on ConnectError",
            function_diffs={"httpx/_client.py::Client._send_single_request": "+    for _ in range(retries):"},
        ),
        UnpackTurn(
            turn_id="T3",
            kind="shell",
            ts="2026-11-20T10:02:00Z",
            command="pytest tests/test_client.py",
            exit_code=0,
            output="18 passed in 0.4s",
        ),
        UnpackTurn(
            turn_id="T4",
            kind="assistant",
            ts="2026-11-20T10:03:00Z",
            text="I've added tests covering both clients.",
        ),
    ]
    session = UnpackSession(
        agent="gemini-cli",
        file_name="session.jsonl",
        turns=turns,
        turns_by_id={t.turn_id: t for t in turns},
    )
    links = {
        "httpx/_client.py::Client._send_single_request": FunctionLink(
            fn_id="httpx/_client.py::Client._send_single_request",
            change_kind="functional",
            source="session",
            edit_turns=["T2"],
            final_edit_turn="T2",
        ),
        "httpx/_client.py::AsyncClient._send_single_request": FunctionLink(
            fn_id="httpx/_client.py::AsyncClient._send_single_request",
            change_kind="functional",
            source="session",
            edit_turns=["T2"],
            final_edit_turn="T2",
        ),
        "httpx/_client.py::doc_only": FunctionLink(
            fn_id="httpx/_client.py::doc_only",
            change_kind="text_only",
            source="session",
            edit_turns=["T2"],
            final_edit_turn="T2",
        ),
    }
    outcome = LinkOutcome(
        links=links,
        sources={k: v.source for k, v in links.items()},
        last_test_run=TestRunFact(turn="T3", command="pytest tests/test_client.py", exit_code=0, summary="18 passed"),
        tested_after_final_edit=True,
        last_edit_turn_id="T2",
        timeline=[],
        reverted_functions=set(),
        test_runs=[],
    )
    graph_nodes = [
        {"id": "httpx/_client.py::Client._send_single_request", "test": {"label": "reached", "count": 18}},
        {"id": "httpx/_client.py::AsyncClient._send_single_request", "test": {"label": "none", "count": 0}},
        {"id": "httpx/_client.py::doc_only", "test": {"label": "none", "count": 0}},
    ]
    return session, outcome, graph_nodes


def test_prompt_builder_skips_text_only_and_trims_shell_output():
    session, outcome, graph_nodes = _make_sample_session()
    built = build_reasoning_prompt(
        session,
        outcome,
        graph_nodes,
        [
            "httpx/_client.py::Client._send_single_request",
            "httpx/_client.py::AsyncClient._send_single_request",
            "httpx/_client.py::doc_only",
        ],
    )
    assert built.alias_to_node == {
        "F1": "httpx/_client.py::Client._send_single_request",
        "F2": "httpx/_client.py::AsyncClient._send_single_request",
    }
    assert built.text_only_node_ids == ["httpx/_client.py::doc_only"]
    assert "## TASK" in built.user_prompt
    assert "## CHANGED FUNCTIONS" in built.user_prompt
    assert "## FACTS (computed, do not contradict)" in built.user_prompt
    assert "Tests that reach F2 (httpx/_client.py::AsyncClient._send_single_request): none" in built.user_prompt
    assert "doc_only" not in built.user_prompt

    # Shell output trimmer preserves head 40, tail 60, and middle FAILED/Error lines
    long_lines = [f"line {i}" for i in range(150)]
    long_lines[75] = "FAILED tests/test_x.py::test_retry"
    trimmed = trim_shell_output("\n".join(long_lines))
    assert "line 0" in trimmed
    assert "FAILED tests/test_x.py::test_retry" in trimmed
    assert "line 149" in trimmed
    assert "lines omitted" in trimmed


def test_verifier_enforces_quotes_user_asked_history_turns_and_facts():
    session, outcome, graph_nodes = _make_sample_session()
    alias_to_node = {
        "F1": "httpx/_client.py::Client._send_single_request",
        "F2": "httpx/_client.py::AsyncClient._send_single_request",
    }

    llm_out = LLMReasoningOutput(
        summary="Added retries to sync and async clients.",
        functions=[
            # Valid user_asked with smart quote + whitespace normalization + 1 bad history turn ID
            LLMFunctionReason(
                fn="F1",
                reason="Added retry loop requested by the user.",
                driver="user_asked",
                history=[
                    LLMHistoryStep(turn="T2", text="Wrapped _send_single_request"),
                    LLMHistoryStep(turn="T999", text="Hallucinated turn ID should be pruned"),
                ],
                evidence=[
                    LLMEvidenceQuote(turn="T1", quote="Add retries  to sync and async clients."),
                    LLMEvidenceQuote(turn="T2", quote="Wrap _send_single_request with retry loop"),
                ],
                confidence="high",
            ),
            # Invalid: user_asked citing only an edit turn (no user turn!) -> must downgrade & record rejected
            LLMFunctionReason(
                fn="F2",
                reason="Mirrors sync retries.",
                driver="user_asked",
                history=[LLMHistoryStep(turn="T2", text="Edited async client")],
                evidence=[LLMEvidenceQuote(turn="T2", quote="Wrap _send_single_request")],
                confidence="high",
            ),
        ],
        session_review=[
            # Valid claim_not_backed (F2 really has test.label == "none")
            LLMReviewFinding(
                kind="claim_not_backed",
                finding="Agent claimed tests cover both clients, but no test reaches AsyncClient.",
                functions=["F2"],
                evidence=[LLMEvidenceQuote(turn="T4", quote="I\u2019ve added tests covering both clients.")],
            ),
            # Contradicts FACTS (tested_after_final_edit is True) -> must be dropped
            LLMReviewFinding(
                kind="not_tested_after_change",
                finding="No tests were run after edit.",
                functions=["F1"],
                evidence=[LLMEvidenceQuote(turn="T2", quote="Wrap _send_single_request")],
            ),
            # Contradicts FACTS (F1 IS tested) -> must be dropped
            LLMReviewFinding(
                kind="claim_not_backed",
                finding="No test reaches Client._send_single_request.",
                functions=["F1"],
                evidence=[LLMEvidenceQuote(turn="T4", quote="I've added tests covering both clients.")],
            ),
            # Hallucinated quote -> must be dropped
            LLMReviewFinding(
                kind="dead_end",
                finding="Tried something else.",
                functions=["F1"],
                evidence=[LLMEvidenceQuote(turn="T2", quote="this quote does not exist anywhere")],
            ),
        ],
    )

    verified = verify_reasoning_output(
        llm_out,
        session=session,
        link_outcome=outcome,
        alias_to_node=alias_to_node,
        target_node_ids=list(alias_to_node.values()),
        text_only_node_ids=["httpx/_client.py::doc_only"],
        graph_nodes=graph_nodes,
    )

    # F1 kept, invalid history step T999 pruned while T2 preserved
    f1 = verified.reasons["httpx/_client.py::Client._send_single_request"]
    assert f1["driver"] == "user_asked"
    assert f1["history"] == [{"turn": "T2", "text": "Wrapped _send_single_request"}]
    assert f1["rejected"] is None

    # F2 downgraded to not_stated with hidden rejected payload preserved
    f2 = verified.reasons["httpx/_client.py::AsyncClient._send_single_request"]
    assert f2["driver"] == "not_stated"
    assert f2["reason"] == NO_REASON_TEXT
    assert f2["rejected"] is not None
    assert "user_asked" in f2["rejected"]["reject_reason"]

    # doc_only auto-labelled locally
    doc = verified.reasons["httpx/_client.py::doc_only"]
    assert doc["reason"] == TEXT_ONLY_REASON

    # Only the 1 valid claim_not_backed finding survives; 3 findings + 1 function reason rejected
    assert len(verified.findings) == 1
    assert verified.findings[0]["kind"] == "claim_not_backed"
    assert verified.findings[0]["functions"] == ["httpx/_client.py::AsyncClient._send_single_request"]
    assert verified.rejected_count == 4


@pytest.mark.asyncio
async def test_llm_client_fallback_and_json_repair(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_MODEL_PRIMARY", "gemini-3.1-pro-preview")
    monkeypatch.setattr(settings, "GEMINI_MODEL_FALLBACK", "gemini-2.5-pro")
    monkeypatch.setattr(settings, "GEMINI_MODEL_REPAIR", "gemini-2.5-flash")

    valid_json = json.dumps({"summary": "Done.", "functions": [], "session_review": []})

    # Scenario 1: Primary fails twice -> fallback succeeds (checks temperature rules too)
    fake = _ScriptedLLM(
        [
            LLMBackendError("503 overloaded"),
            LLMBackendError("503 overloaded"),
            RawLLMResponse(text=valid_json, model="gemini-2.5-pro", input_tokens=100, output_tokens=40),
        ]
    )
    res = await run_reasoning_llm(system_prompt="sys", user_prompt="usr", client=fake)
    assert res.output is not None and res.model == "gemini-2.5-pro"
    assert len(res.calls) == 3
    assert fake.calls[0]["temperature"] is None  # Gemini 3 default
    assert fake.calls[2]["temperature"] == 0.0  # Gemini 2.5 deterministic

    # Scenario 2: Primary returns broken JSON -> repair model fixes it
    fake_repair = _ScriptedLLM(
        [
            RawLLMResponse(text="{not valid json", model="gemini-3.1-pro-preview", input_tokens=50, output_tokens=10),
            RawLLMResponse(text=valid_json, model="gemini-2.5-flash", input_tokens=60, output_tokens=30),
        ]
    )
    res2 = await run_reasoning_llm(system_prompt="sys", user_prompt="usr", client=fake_repair)
    assert res2.output is not None
    assert [c.purpose for c in res2.calls] == ["reasons", "json_repair"]

    # Scenario 3: Daily token budget exceeded -> skips API completely
    res3 = await run_reasoning_llm(
        system_prompt="sys",
        user_prompt="usr",
        daily_tokens_used=settings.GEMINI_DAILY_TOKEN_BUDGET_PER_REPO,
        client=fake,
    )
    assert res3.output is None and "budget" in (res3.error or "")
