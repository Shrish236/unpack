"""Antigravity CLI (agy) transcript parsing against a captured session and synthetic tool calls."""

from __future__ import annotations

import json
from pathlib import Path

from server.app.pipeline.agy_session import AGY_AGENT, parse_agy_transcript

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "agy" / "say_hi_transcript_full.jsonl"


def _records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _payload(lines: list[dict]) -> dict:
    return {"agent": AGY_AGENT, "file_name": "transcript_full.jsonl", "lines": lines}


def test_captured_say_hi_session_yields_user_and_assistant_turns():
    session = parse_agy_transcript(_payload(_records(FIXTURE)))

    assert session.agent == AGY_AGENT
    assert [t.kind for t in session.turns] == ["user", "assistant"]
    assert session.turns[0].text == "say hi"
    assert session.turns[1].text == "Hi! How can I help you today?"
    assert session.turns_by_id["T1"] is session.turns[0]


def test_user_prompt_strips_request_wrapper_and_metadata():
    rec = {
        "step_index": 0, "source": "USER_EXPLICIT", "type": "USER_INPUT", "status": "DONE",
        "created_at": "2026-11-20T11:00:00Z",
        "content": "<USER_REQUEST>\nfix the bug\n</USER_REQUEST>\n<ADDITIONAL_METADATA>\nlocal time\n</ADDITIONAL_METADATA>",
    }
    session = parse_agy_transcript(_payload([rec]))
    assert session.turns[0].kind == "user"
    assert session.turns[0].text == "fix the bug"


def test_shell_result_fills_exit_code_and_output_and_edits_are_repo_relative():
    lines = [
        {
            "step_index": 1, "source": "MODEL", "type": "PLANNER_RESPONSE", "status": "DONE",
            "created_at": "2026-11-20T11:01:00Z", "content": "running tests",
            "tool_calls": [{"name": "run_command", "args": {"CommandLine": "python -m pytest -q"}}],
        },
        {
            "step_index": 2, "source": "MODEL", "type": "GENERIC", "status": "DONE",
            "created_at": "2026-11-20T11:01:05Z",
            "content": "Created At: x\nCommand exited with code 1.\n\nCommand output:\n1 failed\r\n",
        },
        {
            "step_index": 3, "source": "MODEL", "type": "PLANNER_RESPONSE", "status": "DONE",
            "created_at": "2026-11-20T11:02:00Z",
            "tool_calls": [{"name": "replace_file_content", "args": {"TargetFile": "/abs/repo/shop/pricing.py"}}],
        },
        {
            "step_index": 4, "source": "MODEL", "type": "GENERIC", "status": "DONE",
            "created_at": "2026-11-20T11:02:01Z", "content": "Edit applied.",
        },
    ]
    session = parse_agy_transcript(_payload(lines), known_paths={"shop/pricing.py"})

    shell = next(t for t in session.turns if t.kind == "shell")
    assert shell.command == "python -m pytest -q"
    assert shell.exit_code == 1
    assert shell.output == "1 failed"

    edit = next(t for t in session.turns if t.kind == "edit")
    assert edit.path == "shop/pricing.py"
    assert edit.tool_name == "replace_file_content"


def test_result_without_matching_call_is_ignored():
    lines = [{"step_index": 0, "type": "GENERIC", "created_at": "t", "content": "orphan"}]
    session = parse_agy_transcript(_payload(lines))
    assert session.turns == []


def test_unknown_record_types_are_skipped():
    lines = [{"step_index": 0, "type": "CHECKPOINT", "created_at": "t", "content": "x"}]
    session = parse_agy_transcript(_payload(lines))
    assert session.turns == []
