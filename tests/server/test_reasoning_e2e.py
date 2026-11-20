"""End-to-end Postgres + worker tests for session parsing, reasoning, verification, and degraded mode."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from sqlalchemy import select

from server.app.config import settings
from server.app.db import session_scope
from server.app.llm.client import LLMBackendError, RawLLMResponse, set_llm_client
from server.app.models import FunctionReason, LLMCall, Session

from .conftest import Origin, drain_jobs
from .helpers import create_repo, gzip_json, ingest_headers, origin_payload, standard_files
from .test_ingest_and_analysis import login

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class _FakeLLM:
    def __init__(self, responses: list[RawLLMResponse | Exception]) -> None:
        self._responses = list(responses)

    async def generate_json(self, **kwargs) -> RawLLMResponse:
        if kwargs["response_schema"].__name__ == "LLMDecisionOutput":  # the governance pass has its own call
            return RawLLMResponse(text='{"decisions": [], "highlights": []}', model="fake-decisions")
        if kwargs["response_schema"].__name__ == "LLMFlowOutput":  # the flow call: F2 first, F1 second
            return RawLLMResponse(text=json.dumps({"stages": [{"title": "Both helpers", "summary": "s", "steps": [
                {"fn": "F2", "role": "entry", "note": "new"}, {"fn": "F1", "role": "logic", "note": "bumped"}]}]}), model="fake-flow")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _demo_session_for_standard_files(base: dict[str, str], head: dict[str, str]) -> dict:
    return {
        "agent": "gemini-cli",
        "agent_version": "0.64.0",
        "file_name": "session-2026-11-20T10-00-abcd1234.jsonl",
        "lines": [
            {
                "sessionId": "abcd1234",
                "projectHash": "demo",
                "startTime": "2026-11-20T10:00:00Z",
                "lastUpdated": "2026-11-20T10:05:00Z",
            },
            {
                "id": "m1",
                "timestamp": "2026-11-20T10:00:05Z",
                "type": "user",
                "content": [{"text": "Bump helper return value and add brand_new helper"}],
            },
            {
                "id": "m2",
                "timestamp": "2026-11-20T10:01:00Z",
                "type": "gemini",
                "content": [{"text": "Updated pkg/core.py and added tests for both functions."}],
                "thoughts": [{"subject": "Edit", "description": "Modify helper and add brand_new"}],
                "toolCalls": [
                    {
                        "id": "tc1",
                        "name": "replace",
                        "args": {
                            "file_path": "pkg/core.py",
                            "instruction": "Change helper to return x + 2 and add brand_new",
                        },
                        "status": "success",
                        "resultDisplay": {
                            "originalContent": base["pkg/core.py"],
                            "newContent": head["pkg/core.py"],
                            "fileDiff": "@@ -1,2 +1,5 @@",
                        },
                    },
                    {
                        "id": "tc2",
                        "name": "run_shell_command",
                        "args": {"command": "pytest tests/test_core.py"},
                        "status": "success",
                        "result": "1 passed in 0.05s\nExit Code: 0",
                    },
                ],
            },
        ],
    }


@pytest.mark.asyncio
async def test_full_reasoning_pipeline_end_to_end(client, tmp_data_dir, tmp_path, fake_github, monkeypatch):
    base, head = standard_files()
    origin = Origin(tmp_path, base, head)
    _, token = await create_repo(remote_url=origin.remote_url)

    payload = origin_payload(origin, session=_demo_session_for_standard_files(base, head))

    # F1 = pkg/core.py::helper, F2 = pkg/core.py::brand_new (per reading_order)
    llm_json = json.dumps(
        {
            "summary": "Bumped helper return value and added brand_new as requested.",
            "functions": [
                {
                    "fn": "F1",
                    "reason": "Incremented helper offset to x + 2 per user request.",
                    "driver": "user_asked",
                    "history": [
                        {"turn": "T4", "text": "Updated helper in pkg/core.py"},
                        {"turn": "T999", "text": "Invalid turn ID should be dropped"},
                    ],
                    "evidence": [
                        {"turn": "T1", "quote": "Bump helper return value"},
                        {"turn": "T4", "quote": "Change helper to return x + 2"},
                    ],
                    "confidence": "high",
                },
                {
                    "fn": "F2",
                    "reason": "Hallucinated quote will force rejection.",
                    "driver": "agent_decided",
                    "history": [],
                    "evidence": [{"turn": "T4", "quote": "nonexistent fabricated quote"}],
                    "confidence": "medium",
                },
            ],
            "session_review": [
                {
                    "kind": "claim_not_backed",
                    "finding": "Agent claimed tests cover both functions, but no test reaches brand_new.",
                    "functions": ["F2"],
                    "evidence": [{"turn": "T3", "quote": "added tests for both functions"}],
                }
            ],
        }
    )

    monkeypatch.setattr(settings, "REASONING_ENABLED", True)
    set_llm_client(_FakeLLM([RawLLMResponse(text=llm_json, model="gemini-3.1-pro-preview", input_tokens=300, output_tokens=120)]))
    try:
        resp = await client.post("/v1/ingest", content=gzip_json(payload), headers=ingest_headers(token))
        assert resp.status_code == 202, resp.text
        public_id = resp.json()["analysis"]["public_id"]

        assert await drain_jobs() >= 1

        await login(client)
        res = await client.get(f"/api/analyses/{public_id}")
        assert res.status_code == 200, res.text
        body = res.json()

        # Validate live API response against exported JSON schema!
        schema = json.loads((REPO_ROOT / "contract" / "schema" / "analysis_response.json").read_text(encoding="utf-8"))
        jsonschema.validate(instance=body, schema=schema)

        assert body["analysis"]["status"] == "done"
        assert body["analysis"]["llm_model"] == "gemini-3.1-pro-preview"
        assert body["banner"] is None
        assert body["summary"].startswith("Bumped helper")

        # Both reading flows are served. The model's puts brand_new first; every changed function is in both.
        flow = body["flow"]
        assert flow["llm"]["mode"] == "llm" and flow["model"] == "fake-flow"
        assert flow["llm"]["order"][:2] == ["pkg/core.py::brand_new", "pkg/core.py::helper"]
        assert sorted(flow["llm"]["order"]) == sorted(flow["deterministic"]["order"])
        assert flow["llm"]["stages"][0]["steps"][0]["role"] == "entry"
        # The file-level diff keeps every hunk and says who owns it.
        owned = {o for f in body["diff_files"] for h in f["hunks"] for o in h["owners"]}
        assert {"pkg/core.py::helper", "pkg/core.py::brand_new"} <= owned
        assert all(h["id"].startswith("pkg/core.py#") for f in body["diff_files"] if f["path"] == "pkg/core.py" for h in f["hunks"])

        # Provenance & facts computed from session
        assert body["stats"]["by_source"]["session"] == 2
        assert body["facts"]["tested_after_final_edit"] is True
        assert body["facts"]["last_test_run"]["command"] == "pytest tests/test_core.py"

        # Structured history verified (T999 pruned, T4 kept)
        helper_reason = body["reasons"]["pkg/core.py::helper"]
        assert helper_reason["driver"] == "user_asked"
        assert helper_reason["history"] == [{"turn": "T4", "text": "Updated helper in pkg/core.py"}]
        assert "rejected" not in helper_reason  # never exposed in public API

        # F2 downgraded to not_stated in API, original rejected payload stored in DB
        brand_new_reason = body["reasons"]["pkg/core.py::brand_new"]
        assert brand_new_reason["driver"] == "not_stated"

        # Finding persisted with real DB ID linked onto graph node AND claim timeline item
        assert len(body["findings"]) == 1
        finding_id = body["findings"][0]["id"]
        nodes = {n["id"]: n for n in body["graph"]["nodes"]}
        assert nodes["pkg/core.py::helper"]["has_reason"] is True
        assert nodes["pkg/core.py::brand_new"]["finding_ids"] == [finding_id]
        claim_items = [t for t in body["timeline"] if t["kind"] == "claim"]
        assert len(claim_items) == 1 and claim_items[0]["finding_id"] == finding_id

        # /turns endpoint serves parsed turns stored in sessions.turns
        turns_res = await client.get(f"/api/analyses/{public_id}/turns?ids=T1,T4,T5")
        assert turns_res.status_code == 200
        turns = {t["turn_id"]: t for t in turns_res.json()["turns"]}
        assert turns["T1"]["kind"] == "user"
        assert turns["T4"]["kind"] == "edit" and turns["T4"]["path"] == "pkg/core.py"
        assert turns["T5"]["kind"] == "shell" and turns["T5"]["exit_code"] == 0

        # Verify DB persistence of rejected reason, Session.turns, and LLMCall row
        async with session_scope() as db:
            fr_rows = (await db.execute(select(FunctionReason))).scalars().all()
            bn_row = next(r for r in fr_rows if r.node_id == "pkg/core.py::brand_new")
            assert bn_row.rejected is not None
            assert bn_row.rejected["reason"] == "Hallucinated quote will force rejection."

            sess_row = (await db.execute(select(Session))).scalar_one()
            assert len(sess_row.turns) >= 5

            llm_rows = (await db.execute(select(LLMCall).where(LLMCall.purpose == "reasons"))).scalars().all()
            assert len(llm_rows) == 1
            assert llm_rows[0].input_tokens == 300 and llm_rows[0].output_tokens == 120
    finally:
        set_llm_client(None)


@pytest.mark.asyncio
async def test_reasoning_degrades_gracefully_when_llm_fails(client, tmp_data_dir, tmp_path, fake_github, monkeypatch):
    base, head = standard_files()
    origin = Origin(tmp_path, base, head)
    _, token = await create_repo(remote_url=origin.remote_url)
    payload = origin_payload(origin, session=_demo_session_for_standard_files(base, head))

    monkeypatch.setattr(settings, "REASONING_ENABLED", True)
    set_llm_client(_FakeLLM([LLMBackendError("GEMINI_API_KEY is not set")]))
    try:
        resp = await client.post("/v1/ingest", content=gzip_json(payload), headers=ingest_headers(token))
        assert resp.status_code == 202
        public_id = resp.json()["analysis"]["public_id"]

        assert await drain_jobs() >= 1

        await login(client)
        res = await client.get(f"/api/analyses/{public_id}")
        assert res.status_code == 200
        body = res.json()

        # Analysis still succeeds with graph, provenance, facts, timeline, and reasons_unavailable banner
        assert body["analysis"]["status"] == "done"
        assert body["banner"]["kind"] == "reasons_unavailable"
        assert body["stats"]["by_source"]["session"] == 2
        assert body["facts"]["tested_after_final_edit"] is True
        # Every changed function still gets a row, marked as not analysed, so the UI has no holes.
        assert body["reasons"]
        assert all(r["reason"].startswith("Not analysed") and r["confidence"] == "low" for r in body["reasons"].values())
        assert all(not n["has_reason"] for n in body["graph"]["nodes"] if n["id"] in body["reasons"])
    finally:
        set_llm_client(None)
