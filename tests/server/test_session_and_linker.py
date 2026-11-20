"""Unit tests for Gemini CLI session replay, edit-to-function linking, test facts, and timeline."""

from __future__ import annotations

from unpack_graph.graph import build_graph

from server.app.pipeline.changes import compute_changes
from server.app.pipeline.edit_linker import link_session_to_changes, parse_test_run
from server.app.pipeline.session import UnpackTurn, parse_gemini_session


class _MemSource:
    def __init__(self, files: dict[str, bytes]) -> None:
        self._files = files

    def list_files(self) -> list[str]:
        return sorted(self._files)

    def read(self, path: str) -> bytes:
        return self._files[path]


def _source(files: dict[str, str]) -> _MemSource:
    return _MemSource({k: v.encode("utf-8") for k, v in files.items()})


def test_replay_gemini_jsonl_patch_rewind_set_and_flatten():
    lines = [
        {
            "sessionId": "sess-1",
            "projectHash": "proj",
            "startTime": "2026-11-20T10:00:00Z",
            "directories": ["/repo/httpx"],
        },
        {"$set": {"lastUpdated": "2026-11-20T10:20:00Z", "summary": "Add retries"}},
        {"id": "m1", "timestamp": "2026-11-20T10:01:00Z", "type": "user", "content": [{"text": "Add retries"}]},
        {
            "id": "m2",
            "timestamp": "2026-11-20T10:02:00Z",
            "type": "gemini",
            "content": "Initial draft",
            "thoughts": [{"subject": "Plan", "description": "Check client"}],
            "toolCalls": [
                {"id": "tc_read", "name": "read_file", "args": {"file_path": "/repo/httpx/pkg/core.py"}},
                {
                    "id": "tc_edit",
                    "name": "replace",
                    "args": {"file_path": "/repo/httpx/pkg/core.py", "instruction": "Update helper"},
                    "status": "success",
                    "resultDisplay": {
                        "originalContent": "def helper():\n    return 1\n",
                        "newContent": "def helper():\n    return 2\n",
                        "fileDiff": "@@ -1,2 +1,2 @@\n-    return 1\n+    return 2",
                    },
                },
            ],
        },
        # Patch updates m2 content and tc_read result
        {"$patch": {"id": "m2", "content": "Updated helper in pkg/core.py"}},
        # Rewound message that must be dropped by $rewindTo
        {"id": "m3", "timestamp": "2026-11-20T10:03:00Z", "type": "user", "content": "Mistaken prompt"},
        {"id": "m4", "timestamp": "2026-11-20T10:04:00Z", "type": "gemini", "content": "Mistaken reply"},
        {"$rewindTo": "m3"},
        # Plan and shell after rewind
        {
            "id": "m5",
            "timestamp": "2026-11-20T10:05:00Z",
            "type": "gemini",
            "content": [{"text": "All tests pass."}],
            "toolCalls": [
                {"id": "tc_plan", "name": "write_todos", "args": {"todos": [{"status": "done", "description": "Add retries"}]}},
                {
                    "id": "tc_sh",
                    "name": "run_shell_command",
                    "args": {"command": "pytest tests/test_core.py"},
                    "status": "success",
                    "result": "=== 5 passed in 0.12s ===\nExit Code: 0",
                },
            ],
        },
    ]

    session = parse_gemini_session(
        {"agent": "gemini-cli", "file_name": "session-1.jsonl", "lines": lines},
        known_paths={"pkg/core.py"},
    )
    assert session.last_updated == "2026-11-20T10:20:00Z"
    assert session.summary == "Add retries"

    kinds = [(t.turn_id, t.kind) for t in session.turns]
    assert kinds == [
        ("T1", "user"),
        ("T2", "thought"),
        ("T3", "assistant"),
        ("T4", "read"),
        ("T5", "edit"),
        ("T6", "assistant"),
        ("T7", "plan"),
        ("T8", "shell"),
    ]
    assert session.turns_by_id["T3"].text == "Updated helper in pkg/core.py"
    assert session.turns_by_id["T5"].path == "pkg/core.py"
    assert session.turns_by_id["T5"].instruction == "Update helper"
    assert session.turns_by_id["T8"].exit_code == 0
    # Rewound messages are absent
    assert all("Mistaken" not in t.text for t in session.turns)

    details = session.to_turn_details()
    assert details[0]["turn_id"] == "T1" and details[0]["kind"] == "user"


def test_edit_linker_provenance_out_of_band_reverted_and_test_facts():
    base_code = (
        "def keep_reverted():\n    return 0\n\n"
        "def session_fn():\n    return 1\n\n"
        "def formatted_fn():\n    return 10\n\n"
        "def partial_fn():\n    return 20\n\n"
        "def outside_fn():\n    return 30\n"
    )
    # Edit 1: tries touching keep_reverted (will be reverted later) and session_fn
    after_edit1 = (
        "def keep_reverted():\n    return 999\n\n"
        "def session_fn():\n    return 2\n\n"
        "def formatted_fn():\n    return 10\n\n"
        "def partial_fn():\n    return 20\n\n"
        "def outside_fn():\n    return 30\n"
    )
    # Edit 2: reverts keep_reverted, updates formatted_fn and partial_fn
    after_edit2 = (
        "def keep_reverted():\n    return 0\n\n"
        "def session_fn():\n    return 2\n\n"
        "def formatted_fn():\n    return  11\n\n"  # extra space before ruff format
        "def partial_fn():\n    return 21\n\n"
        "def outside_fn():\n    return 30\n"
    )
    # Final committed head:
    # - session_fn matches Edit 1 exactly -> session
    # - formatted_fn reformatted by ruff (same logic_hash, different text_hash) -> session_then_formatted
    # - partial_fn logic changed again manually (21 -> 22) -> session_partial
    # - outside_fn changed manually (30 -> 31), never touched in session -> outside_session
    head_code = (
        "def keep_reverted():\n    return 0\n\n"
        "def session_fn():\n    return 2\n\n"
        "def formatted_fn():\n    # formatted\n    return 11\n\n"
        "def partial_fn():\n    return 22\n\n"
        "def outside_fn():\n    return 31\n"
    )

    base_graph = build_graph(_source({"pkg/mod.py": base_code}), reach=False)
    head_graph = build_graph(_source({"pkg/mod.py": head_code}), reach=True)
    changes = compute_changes(base_graph, head_graph)

    session_lines = [
        {"sessionId": "s2", "projectHash": "p", "startTime": "2026-11-20T10:00:00Z"},
        {"id": "u1", "timestamp": "2026-11-20T10:00:01Z", "type": "user", "content": "Update functions"},
        {
            "id": "g1",
            "timestamp": "2026-11-20T10:01:00Z",
            "type": "gemini",
            "content": "",
            "toolCalls": [
                {
                    "id": "e1",
                    "name": "replace",
                    "args": {"file_path": "pkg/mod.py", "instruction": "Edit keep_reverted and session_fn"},
                    "status": "success",
                    "resultDisplay": {"originalContent": base_code, "newContent": after_edit1},
                },
                {
                    "id": "sh1",
                    "name": "run_shell_command",
                    "args": {"command": "pytest tests/test_mod.py"},
                    "status": "error",
                    "result": "FAILED tests/test_mod.py::test_x\n1 failed, 2 passed in 0.2s\nExit Code: 1",
                },
                {
                    "id": "e2",
                    "name": "replace",
                    "args": {"file_path": "pkg/mod.py", "instruction": "Revert keep_reverted, update formatted_fn and partial_fn"},
                    "status": "success",
                    "resultDisplay": {"originalContent": after_edit1, "newContent": after_edit2},
                },
                {
                    "id": "sh_fmt",
                    "name": "run_shell_command",
                    "args": {"command": "ruff format pkg/mod.py"},
                    "status": "success",
                    "result": "1 file reformatted\nExit Code: 0",
                },
                {
                    "id": "sh2",
                    "name": "run_shell_command",
                    "args": {"command": "pytest tests/test_mod.py"},
                    "status": "success",
                    "result": "3 passed in 0.1s\nExit Code: 0",
                },
            ],
        },
    ]
    session = parse_gemini_session(
        {"agent": "gemini-cli", "file_name": "session-2.jsonl", "lines": session_lines},
        known_paths={"pkg/mod.py"},
    )
    linked = link_session_to_changes(
        session,
        changes,
        base_graph,
        head_graph,
        [{"path": "pkg/mod.py", "status": "M", "base_content": base_code, "head_content": head_code}],
    )

    assert linked.sources["pkg/mod.py::session_fn"] == "session"
    assert linked.sources["pkg/mod.py::formatted_fn"] == "session_then_formatted"
    assert linked.sources["pkg/mod.py::partial_fn"] == "session_partial"
    assert linked.sources["pkg/mod.py::outside_fn"] == "outside_session"
    assert "pkg/mod.py::keep_reverted" in linked.reverted_functions

    assert linked.last_test_run is not None
    assert linked.last_test_run.exit_code == 0
    assert "3 passed" in linked.last_test_run.summary
    assert linked.tested_after_final_edit is True


def test_parse_test_run_recognizes_python_runners():
    u_turn = UnpackTurn(
        turn_id="T9",
        kind="shell",
        command="python3 -m unittest discover -s tests",
        exit_code=0,
        output="Ran 12 tests in 0.42s\n\nOK",
    )
    fact = parse_test_run(u_turn)
    assert fact is not None
    assert fact.exit_code == 0
    assert "12 tests" in fact.summary

    non_test = UnpackTurn(turn_id="T10", kind="shell", command="ruff format .", exit_code=0, output="")
    assert parse_test_run(non_test) is None
