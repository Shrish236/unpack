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

from .session import UnpackSession, UnpackTurn, is_denied, normalize_repo_path

AGY_AGENT = "antigravity-cli"

EDIT_TOOL_NAMES = frozenset({"edit_file", "replace_file_content", "multi_replace_file_content", "write_to_file"})
SHELL_TOOL_NAMES = frozenset({"run_command"})
READ_TOOL_NAMES = frozenset({"read_file", "view_file", "list_dir", "grep_search", "find_by_name", "read_url_content"})

_USER_REQUEST_RE = re.compile(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", re.DOTALL)
_EXIT_CODE_RE = re.compile(r"Command exited with code (-?\d+)")
_OUTPUT_RE = re.compile(r"Command output:\r?\n(.*)", re.DOTALL)
_EDIT_PATH_KEYS = ("Path", "TargetFile", "AbsolutePath", "file_path", "path")
_READ_PATH_KEYS = ("Path", "AbsolutePath", "DirectoryPath", "SearchPath", "SearchDirectory", "file_path", "path")


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _text_raw(value: Any) -> str | None:
    """Edit text keeps its whitespace: an indentation change is a real change."""
    return value if isinstance(value, str) else None


def _snippet_diff(path: str | None, old: str | None, new: str | None) -> str:
    import difflib

    return "".join(difflib.unified_diff(
        (old or "").splitlines(keepends=True), (new or "").splitlines(keepends=True),
        fromfile=f"a/{path or 'file'}", tofile=f"b/{path or 'file'}", n=1,
    ))


def reconstruct_edit_states(session: UnpackSession, base_contents: dict[str, str]) -> int:
    """Fill original_content and new_content on snippet edits by replaying them over the base files.

    The edit linker compares whole-file states. A snippet edit (Target -> Replacement) carries only the
    snippet, so the state is rebuilt by applying each edit, in order, to the file as it stood. Returns how many
    edits could be replayed. An edit whose Target is not in the file is left without a state and is not linked.
    """
    current: dict[str, str] = {}
    done = 0
    for turn in session.turns:
        if turn.kind != "edit" or turn.edit_new is None or not turn.path:
            continue
        if (turn.status or "").upper() in ("ERROR", "CANCELED", "CANCELLED"):
            continue
        before = current.get(turn.path, base_contents.get(turn.path))
        if before is None:
            continue
        if turn.edit_old:
            if turn.edit_old not in before:
                continue
            after = before.replace(turn.edit_old, turn.edit_new, 1)
        else:  # no Target: the Replacement is the whole new file
            after = turn.edit_new
        turn.original_content, turn.new_content = before, after
        current[turn.path] = after
        done += 1
    return done


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
            rec_tokens = int(rec.get("input_tokens") or 0) + int(rec.get("output_tokens") or 0)
            per_call_tokens = (rec_tokens // len(tool_calls)) or None
            for call in tool_calls:
                first_new = len(turns)
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
                    old, new = _text_raw(args.get("Target")), _text_raw(args.get("Replacement"))
                    pending.append(add_turn(
                        "edit", ts=ts, path=rel, tool_name=name, edit_old=old, edit_new=new,
                        file_diff=_snippet_diff(rel, old, new) if (old is not None or new is not None) else None,
                        text=f"{name} {rel}" if rel else name,
                    ))
                elif name in READ_TOOL_NAMES:
                    raw = _first_arg(args, _READ_PATH_KEYS)
                    rel = normalize_repo_path(raw, [], paths_set) if raw else None
                    pending.append(add_turn("read", ts=ts, path=rel, tool_name=name, text=f"{name} {rel or raw or ''}".strip()))
                else:
                    pending.append(None)
                for new_turn in turns[first_new:]:
                    new_turn.tokens = per_call_tokens
            continue

        if rec_type == "GENERIC":
            if not pending:
                continue
            shell_turn = pending.popleft()
            if shell_turn is None:
                continue
            content = _text(rec.get("content"))
            shell_turn.status = str(rec.get("status") or "") or None
            shell_turn.denied = is_denied(shell_turn.status, f"{_text(rec.get('error'))} {content}")
            if shell_turn.kind != "shell":  # edit or read: only the outcome matters
                continue
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
