"""Antigravity CLI (agy) transcript replay: transcript_full.jsonl step records -> UnpackSession.

Record shapes (observed from agy 1.5.13 sessions):
- ``USER_INPUT``: ``content`` wraps the prompt in ``<USER_REQUEST>...</USER_REQUEST>``.
- ``PLANNER_RESPONSE``: ``content`` (assistant text), optional ``thinking``, optional
  ``tool_calls`` as ``[{"name": ..., "args": {...}}]``, plus ``model`` and token counts.
- ``GENERIC``: a tool result. ``content`` holds "Command exited with code N." and
  "Command output:" for shell calls. One result follows each tool call, in call order.

The file has no working-directory field, so the CLI finds the file by conversation id
(cli/agy_session.py). Undocumented layouts are verified against captured sessions in tests.
"""

from __future__ import annotations

import re
from collections import deque
from typing import Any

from .session import UnpackSession, UnpackTurn, normalize_repo_path

AGY_AGENT = "antigravity-cli"

EDIT_TOOL_NAMES = frozenset({"replace_file_content", "multi_replace_file_content", "write_to_file"})
SHELL_TOOL_NAMES = frozenset({"run_command"})
READ_TOOL_NAMES = frozenset({"view_file", "list_dir", "grep_search", "find_by_name", "read_url_content"})

_USER_REQUEST_RE = re.compile(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", re.DOTALL)
_EXIT_CODE_RE = re.compile(r"Command exited with code (-?\d+)")
_OUTPUT_RE = re.compile(r"Command output:\r?\n(.*)", re.DOTALL)
_EDIT_PATH_KEYS = ("TargetFile", "AbsolutePath", "file_path", "path")
_READ_PATH_KEYS = ("AbsolutePath", "DirectoryPath", "SearchPath", "SearchDirectory", "file_path", "path")


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _first_arg(args: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = _text(args.get(key))
        if value:
            return value
    return None


def parse_agy_transcript(
    session_payload: dict[str, Any],
    *,
    known_paths: set[str] | None = None,
) -> UnpackSession:
    """Parse an agy SessionPayload (``lines`` = transcript_full.jsonl records) into turns T1..Tn."""
    agent = str(session_payload.get("agent") or AGY_AGENT)
    file_name = str(session_payload.get("file_name") or "transcript_full.jsonl")
    lines = session_payload.get("lines") or []
    paths_set = known_paths or set()

    turns: list[UnpackTurn] = []
    # Tool calls in order; each GENERIC result fills the oldest entry still waiting for one.
    pending: deque[UnpackTurn | None] = deque()
    timestamps: list[str] = []

    def add_turn(kind: str, **kwargs: Any) -> UnpackTurn:
        turn = UnpackTurn(turn_id=f"T{len(turns) + 1}", kind=kind, **kwargs)
        turns.append(turn)
        return turn

    for rec in lines:
        if not isinstance(rec, dict):
            continue
        rec_type = str(rec.get("type") or "")
        ts = str(rec.get("created_at") or "")
        if ts:
            timestamps.append(ts)

        if rec_type == "USER_INPUT":
            content = _text(rec.get("content"))
            match = _USER_REQUEST_RE.search(content)
            text = match.group(1).strip() if match else content
            if text:
                add_turn("user", ts=ts, text=text)
            continue

        if rec_type == "PLANNER_RESPONSE":
            thinking = _text(rec.get("thinking"))
            if thinking:
                add_turn("thought", ts=ts, text=thinking)
            content = _text(rec.get("content"))
            if content:
                add_turn("assistant", ts=ts, text=content)
            tool_calls = rec.get("tool_calls")
            if not isinstance(tool_calls, list):
                continue
            for call in tool_calls:
                if not isinstance(call, dict):
                    continue
                name = str(call.get("name") or "")
                args = call.get("args") if isinstance(call.get("args"), dict) else {}
                if name in SHELL_TOOL_NAMES:
                    command = _first_arg(args, ("CommandLine",)) or ""
                    pending.append(
                        add_turn("shell", ts=ts, command=command, tool_name=name, text=command)
                    )
                elif name in EDIT_TOOL_NAMES:
                    raw = _first_arg(args, _EDIT_PATH_KEYS)
                    rel = normalize_repo_path(raw, [], paths_set) if raw else None
                    add_turn(
                        "edit", ts=ts, path=rel, tool_name=name,
                        text=f"{name} {rel}" if rel else name,
                    )
                    pending.append(None)
                elif name in READ_TOOL_NAMES:
                    raw = _first_arg(args, _READ_PATH_KEYS)
                    rel = normalize_repo_path(raw, [], paths_set) if raw else None
                    add_turn("read", ts=ts, path=rel, tool_name=name, text=f"{name} {rel or raw or ''}".strip())
                    pending.append(None)
                else:
                    pending.append(None)
            continue

        if rec_type == "GENERIC":
            if not pending:
                continue
            shell_turn = pending.popleft()
            if shell_turn is None:
                continue
            content = _text(rec.get("content"))
            exit_match = _EXIT_CODE_RE.search(content)
            if exit_match:
                shell_turn.exit_code = int(exit_match.group(1))
            output_match = _OUTPUT_RE.search(content)
            shell_turn.output = output_match.group(1).strip() if output_match else (content or None)

    return UnpackSession(
        agent=agent,
        file_name=file_name,
        session_id="",
        start_time=timestamps[0] if timestamps else "",
        last_updated=timestamps[-1] if timestamps else "",
        summary=None,
        directories=[],
        turns=turns,
        turns_by_id={t.turn_id: t for t in turns},
    )
