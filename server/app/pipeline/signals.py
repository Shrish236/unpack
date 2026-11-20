"""Deterministic session signals. No LLM: everything here is read from the parsed session and the diff.

These are the facts the dashboards can state with no model in the loop: tool use and tokens, tool calls the
human refused, how many attempts the work took, and flags such as a new dependency or a skipped test.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Any

from .session import UnpackSession, UnpackTurn

MANIFESTS = (
    "requirements.txt", "requirements-dev.txt", "pyproject.toml", "setup.py", "setup.cfg", "pipfile",
    "package.json", "go.mod", "cargo.toml", "pom.xml", "build.gradle", "gemfile",
)
_DEP_LINE_RE = re.compile(r'^\+\s*(?:"?[A-Za-z0-9_.\-@/]+"?\s*(?:[=<>~!]=?|:)\s*"?[\w.^~*<>=,\- ]+"?,?|[A-Za-z0-9_.\-]+(?:[=<>~!]=.*)?)\s*$')
_SKIP_RE = re.compile(r"(@pytest\.mark\.(skip|xfail)|pytest\.skip\(|\.skip\(|\bxit\(|\bxdescribe\(|@unittest\.skip|t\.Skip\()")
_FAIL_RE = re.compile(r"(?i)\b(failed|error|traceback)\b")
TEST_CMD_RE = re.compile(r"(?i)\b(pytest|unittest|npm (run )?test|yarn test|go test|cargo test|jest|vitest|mvn test|gradle test)\b")


def _added_lines_by_file(diff_text: str) -> dict[str, list[str]]:
    files: dict[str, list[str]] = defaultdict(list)
    current: str | None = None
    for line in (diff_text or "").splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            current = path[2:] if path.startswith("b/") else path
        elif current and line.startswith("+") and not line.startswith("+++"):
            files[current].append(line)
    return files


def _flags(session: UnpackSession, diff_text: str) -> list[dict[str, str]]:
    flags: list[dict[str, str]] = []
    added = _added_lines_by_file(diff_text)
    # Edit turns count too, because the diff only holds what survived to the pushed commit.
    for turn in session.turns:
        if turn.kind == "edit" and turn.path and turn.file_diff:
            added.setdefault(turn.path, []).extend(
                l for l in turn.file_diff.splitlines() if l.startswith("+") and not l.startswith("+++")
            )
    for path, lines in added.items():
        base = path.rsplit("/", 1)[-1].lower()
        if base in MANIFESTS:
            dep_lines = [l for l in lines if _DEP_LINE_RE.match(l) and not l.lstrip("+ ").startswith(("#", "[", "version", "name"))]
            if dep_lines:
                flags.append({"flag": "new-dependency", "path": path, "detail": dep_lines[0][1:].strip()[:120]})
        if "test" in path.lower():
            skipped = [l for l in lines if _SKIP_RE.search(l)]
            if skipped:
                flags.append({"flag": "skipped-test", "path": path, "detail": skipped[0][1:].strip()[:120]})
    seen: set[tuple[str, str]] = set()
    unique = []
    for f in flags:
        key = (f["flag"], f["path"])
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique


def _attempts(turns: list[UnpackTurn]) -> int:
    """1 for the first try, plus one for each failing test run that was followed by another edit."""
    attempts = 1
    failing_pending = False
    for t in turns:
        if t.kind == "shell" and TEST_CMD_RE.search(t.command or "") and (t.exit_code not in (0, None)):
            failing_pending = True
        elif t.kind == "edit" and failing_pending:
            attempts += 1
            failing_pending = False
    return attempts


def session_key(session: UnpackSession) -> str:
    """Identity of one agent conversation, the same on every push that carries it.

    A conversation is pushed again each time the branch is pushed, so metrics must count it once.
    Gemini CLI has a session id. Antigravity transcripts have none, so the first request and the first
    timestamp stand in for it.
    """
    first_user = next((t for t in session.turns if t.kind == "user"), None)
    basis = session.session_id or f"{first_user.text if first_user else ''}|{session.start_time or (first_user.ts if first_user else '')}"
    return hashlib.sha1(f"{session.agent}|{basis}".encode("utf-8")).hexdigest()[:16]


def compute_signals(session: UnpackSession, diff_text: str = "") -> dict[str, Any]:
    tools: dict[str, dict[str, int]] = {}
    denied: list[dict[str, Any]] = []
    for t in session.turns:
        if not t.tool_name:
            continue
        row = tools.setdefault(t.tool_name, {"calls": 0, "tokens": 0})
        row["calls"] += 1
        row["tokens"] += t.tokens or 0
        if t.denied:
            denied.append({
                "turn": t.turn_id, "tool": t.tool_name,
                "target": (t.command or t.path or t.text or "")[:200],
            })

    user_turns = [t for t in session.turns if t.kind == "user"]
    shell_fail = sum(1 for t in session.turns if t.kind == "shell" and t.exit_code not in (0, None))
    return {
        "agent": session.agent,
        "session_key": session_key(session),
        "turns": len(session.turns),
        "user_turns": len(user_turns),
        "tool_stats": tools,
        "denied": denied,
        "attempts": _attempts(session.turns),
        "shell_failures": shell_fail,
        "edits": sum(1 for t in session.turns if t.kind == "edit"),
        "flags": _flags(session, diff_text),
    }
