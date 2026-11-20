"""Claude Code transcript -> Gemini format: edits replayed from the base commit, and the server can read the result."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from cli.adapters.claude_code import convert_claude_code, is_claude_code_transcript
from cli.session_finder import load_and_trim_session
from server.app.pipeline.session import parse_gemini_session


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


def _transcript(path: Path, repo: Path) -> None:
    f = str(repo / "m.py")
    rec = lambda t, msg, **kw: {"type": t, "sessionId": "s1", "cwd": str(repo), "timestamp": "2026-11-20T10:00:00Z", "message": msg, **kw}
    rows = [
        rec("user", {"role": "user", "content": "<system-reminder>noise</system-reminder>Add a retry to run()"}),
        rec("assistant", {"role": "assistant", "content": [
            {"type": "text", "text": "I'll add a retry loop to run()."},
            {"type": "tool_use", "id": "t1", "name": "Edit", "input": {"file_path": f, "old_string": "return 1", "new_string": "return retry(1)"}},
        ]}),
        rec("user", {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]}),
        rec("assistant", {"role": "assistant", "content": [{"type": "tool_use", "id": "t2", "name": "Bash", "input": {"command": "pytest"}}]}),
        rec("user", {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t2", "content": "Exit code 1\nFAILED", "is_error": True}]}),
        rec("assistant", {"role": "assistant", "content": [{"type": "text", "text": "side chain"}]}, isSidechain=True),
        rec("assistant", {"role": "assistant", "content": [
            {"type": "tool_use", "id": "t3", "name": "Edit", "input": {"file_path": str(repo / "style.css"), "old_string": "a", "new_string": "b"}}]}),
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows))


def test_heredoc_writes_become_write_turns(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    cmd = "cd " + str(repo) + " && cat > pkg/new.py <<'EOF'\ndef f():\n    return 2\nEOF\npytest -q"
    src = tmp_path / "t.jsonl"
    row = {"type": "assistant", "sessionId": "s", "cwd": str(repo), "timestamp": "2026-11-20T10:00:00Z", "message": {
        "role": "assistant", "content": [{"type": "tool_use", "id": "b1", "name": "Bash", "input": {"command": cmd}}]}}
    src.write_text(json.dumps(row))

    calls = convert_claude_code(src, repo_root=repo)[1]["toolCalls"]

    assert [c["name"] for c in calls] == ["write_file", "run_shell_command"]  # the write comes before the command
    shown = calls[0]["resultDisplay"]
    assert shown["isNewFile"] and shown["newContent"] == "def f():\n    return 2\n"
    assert calls[0]["args"]["file_path"] == str(repo / "pkg" / "new.py")


def test_convert_replays_edits_from_the_base_commit(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "m.py").write_text("def run():\n    return 1\n")
    _git(repo, "add", "."); _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base")
    base = _git(repo, "rev-parse", "HEAD")
    src = tmp_path / "t.jsonl"
    _transcript(src, repo)

    assert is_claude_code_transcript(src)
    lines = convert_claude_code(src, repo_root=repo, base_sha=base)

    assert lines[0]["sessionId"] == "s1" and lines[0]["directories"] == [str(repo)]
    user = lines[1]
    assert user["type"] == "user" and user["content"][0]["text"] == "Add a retry to run()"  # reminder stripped
    edit = lines[2]["toolCalls"][0]
    assert edit["name"] == "replace" and edit["args"]["instruction"] == "I'll add a retry loop to run()."
    assert edit["resultDisplay"]["originalContent"] == "def run():\n    return 1\n"
    assert edit["resultDisplay"]["newContent"] == "def run():\n    return retry(1)\n"
    shell = lines[3]["toolCalls"][0]
    assert shell["status"] == "error" and "Exit code 1" in shell["result"]
    css = lines[-1]["toolCalls"][0]["resultDisplay"]
    assert "originalContent" not in css and css["fileDiff"]  # non-Python files carry a diff only
    assert all("side chain" not in json.dumps(l) for l in lines)  # sub-agent chatter is skipped

    payload = load_and_trim_session(src, repo_root=repo, base_sha=base)
    assert payload["agent"] == "claude-code"
    session = parse_gemini_session(payload, known_paths={"m.py"})
    kinds = [t.kind for t in session.turns]
    assert kinds[:2] == ["user", "assistant"] and "edit" in kinds and "shell" in kinds
    shell_turn = next(t for t in session.turns if t.kind == "shell")
    assert shell_turn.exit_code == 1
    edit_turn = next(t for t in session.turns if t.kind == "edit" and t.path == "m.py")
    assert edit_turn.original_content and edit_turn.new_content
