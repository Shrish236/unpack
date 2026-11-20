"""Gemini CLI JSONL session replay and agent-neutral UnpackSession model (§4.2)."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any

EDIT_TOOL_NAMES = frozenset({"replace", "write_file"})
SHELL_TOOL_NAMES = frozenset({"run_shell_command"})
READ_TOOL_NAMES = frozenset(
    {"read_file", "grep", "search_file_content", "glob", "list_directory", "read_many_files"}
)
PLAN_TOOL_NAMES = frozenset({"write_todos"})

_EXIT_CODE_RE = re.compile(r"(?im)(?:^|\b)exit\s*code\s*[:=]\s*(-?\d+)\b")


@dataclass
class UnpackTurn:
    """One normalized turn in an agent-neutral UnpackSession."""

    turn_id: str
    kind: str  # user | assistant | thought | edit | shell | read | plan | notice
    ts: str = ""
    text: str = ""
    path: str | None = None
    instruction: str | None = None
    status: str | None = None
    original_content: str | None = None
    new_content: str | None = None
    file_diff: str | None = None
    is_new_file: bool = False
    command: str | None = None
    exit_code: int | None = None
    output: str | None = None
    tool_name: str | None = None
    level: str | None = None  # info | error | warning (for notice turns)
    function_diffs: dict[str, str] = field(default_factory=dict)

    def searchable_texts(self) -> list[str]:
        """Return text fields eligible for verbatim quote matching (§4.8)."""
        if self.kind == "edit":
            texts: list[str] = []
            if self.instruction:
                texts.append(self.instruction)
            for diff in self.function_diffs.values():
                if diff:
                    texts.append(diff)
            if self.file_diff:
                texts.append(self.file_diff)
            if self.text:
                texts.append(self.text)
            return texts
        if self.kind == "shell":
            return [t for t in (self.command, self.output, self.text) if t]
        return [t for t in (self.text, self.instruction, self.path) if t]

    def to_turn_detail(self) -> dict[str, Any]:
        """Serialize to TurnDetail dict stored in sessions.turns and served at /turns."""
        excerpt: str | None = None
        if self.kind == "shell" and self.output:
            excerpt = self.output[:1000]
        elif self.kind == "edit" and self.file_diff:
            excerpt = self.file_diff[:1000]
        elif self.kind == "read" and self.text:
            excerpt = self.text[:400]

        return {
            "turn_id": self.turn_id,
            "kind": self.kind,
            "ts": self.ts,
            "path": self.path,
            "instruction": self.instruction,
            "text": self.text or None,
            "command": self.command,
            "exit_code": self.exit_code,
            "excerpt": excerpt,
        }


@dataclass
class UnpackSession:
    """Agent-neutral parsed session with stable T1..Tn turn IDs."""

    agent: str
    file_name: str
    session_id: str = ""
    start_time: str = ""
    last_updated: str = ""
    summary: str | None = None
    directories: list[str] = field(default_factory=list)
    turns: list[UnpackTurn] = field(default_factory=list)
    turns_by_id: dict[str, UnpackTurn] = field(default_factory=dict)

    def to_turn_details(self) -> list[dict[str, Any]]:
        return [t.to_turn_detail() for t in self.turns]


def _extract_part_text(content: Any) -> str:
    """Flatten Gemini PartListUnion (str or list of parts/dicts) to plain text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        if isinstance(content.get("text"), str):
            return content["text"]
        if "functionResponse" in content and isinstance(content["functionResponse"], dict):
            resp = content["functionResponse"].get("response")
            return _extract_part_text(resp)
        if "output" in content and isinstance(content["output"], str):
            return content["output"]
        if "result" in content:
            return _extract_part_text(content["result"])
        return ""
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            chunk = _extract_part_text(item)
            if chunk:
                parts.append(chunk)
        return "\n".join(parts)
    return str(content)


def _apply_tool_updates(existing: list[dict[str, Any]], updates: list[Any]) -> list[dict[str, Any]]:
    by_id: dict[str, int] = {}
    out = [copy.deepcopy(tc) if isinstance(tc, dict) else tc for tc in existing]
    for idx, tc in enumerate(out):
        if isinstance(tc, dict) and tc.get("id"):
            by_id[str(tc["id"])] = idx
    for upd in updates:
        if not isinstance(upd, dict):
            continue
        tc_id = str(upd.get("id") or "")
        if tc_id and tc_id in by_id:
            target = out[by_id[tc_id]]
            for k, v in upd.items():
                if v is not None:
                    target[k] = copy.deepcopy(v)
        else:
            out.append(copy.deepcopy(upd))
            if tc_id:
                by_id[tc_id] = len(out) - 1
    return out


def _apply_message_patch(msg: dict[str, Any], patch_obj: dict[str, Any]) -> None:
    for key, val in patch_obj.items():
        if key in ("id", "updates", "removeIds", "orderIds"):
            continue
        if key == "toolCalls" and isinstance(val, list):
            existing = msg.get("toolCalls") if isinstance(msg.get("toolCalls"), list) else []
            msg["toolCalls"] = _apply_tool_updates(existing, val)
        else:
            msg[key] = copy.deepcopy(val)


def replay_gemini_jsonl(lines: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Replay Gemini CLI append-only JSONL records into (header_meta, ordered_messages)."""
    meta: dict[str, Any] = {}
    messages: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    for rec in lines:
        if not isinstance(rec, dict):
            continue

        if "$set" in rec and isinstance(rec["$set"], dict):
            meta.update(copy.deepcopy(rec["$set"]))
            continue

        if "$rewindTo" in rec:
            target_id = rec["$rewindTo"]
            if target_id in order:
                cut = order.index(target_id)
                for mid in order[cut:]:
                    messages.pop(mid, None)
                order = order[:cut]
            else:
                messages.clear()
                order.clear()
            continue

        if "$patch" in rec and isinstance(rec["$patch"], dict):
            patch = rec["$patch"]
            if isinstance(patch.get("id"), str) and patch["id"] in messages:
                _apply_message_patch(messages[patch["id"]], patch)
            if isinstance(patch.get("updates"), list):
                for upd in patch["updates"]:
                    if isinstance(upd, dict) and isinstance(upd.get("id"), str):
                        mid = upd["id"]
                        if mid in messages:
                            _apply_message_patch(messages[mid], upd)
            if isinstance(patch.get("removeIds"), list):
                remove_set = {str(x) for x in patch["removeIds"]}
                for mid in remove_set:
                    messages.pop(mid, None)
                order = [mid for mid in order if mid not in remove_set]
            if isinstance(patch.get("orderIds"), list):
                new_order: list[str] = []
                seen: set[str] = set()
                for mid in patch["orderIds"]:
                    mid_s = str(mid)
                    if mid_s in messages and mid_s not in seen:
                        new_order.append(mid_s)
                        seen.add(mid_s)
                for mid in order:
                    if mid in messages and mid not in seen:
                        new_order.append(mid)
                        seen.add(mid)
                order = new_order
            continue

        # Header record (has sessionId + projectHash and no message id)
        if "sessionId" in rec and "id" not in rec:
            meta.update(copy.deepcopy(rec))
            continue

        # Message record
        msg_id = rec.get("id")
        if isinstance(msg_id, str) and msg_id:
            if msg_id not in messages:
                order.append(msg_id)
            messages[msg_id] = copy.deepcopy(rec)

    ordered = [messages[mid] for mid in order if mid in messages]
    return meta, ordered


def normalize_repo_path(
    raw_path: str | None,
    directories: list[str],
    known_paths: set[str],
) -> str | None:
    """Convert an absolute or tool-provided file path into a repo-relative POSIX path."""
    if not raw_path:
        return None
    cleaned = raw_path.strip().replace("\\", "/")
    if cleaned.startswith("./"):
        cleaned = cleaned[2:]
    if cleaned in known_paths:
        return cleaned

    for root in directories:
        prefix = root.rstrip("/").replace("\\", "/") + "/"
        if cleaned.startswith(prefix):
            return cleaned[len(prefix) :]

    # Match longest known repo-relative path suffix (e.g., /abs/repo/httpx/_client.py)
    if cleaned.startswith("/"):
        for candidate in sorted(known_paths, key=len, reverse=True):
            if cleaned.endswith("/" + candidate):
                return candidate

    return cleaned


def _parse_shell_exit_code(status: str | None, output: str) -> int | None:
    m = _EXIT_CODE_RE.search(output)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    lowered = (status or "").lower()
    if lowered in ("success", "succeeded", "ok", "completed"):
        return 0
    if lowered in ("error", "failed", "failure"):
        return 1
    return None


def _format_todos(args: dict[str, Any]) -> str:
    todos = args.get("todos")
    if not isinstance(todos, list):
        return ""
    lines: list[str] = []
    for item in todos:
        if isinstance(item, dict):
            status = item.get("status", "")
            desc = item.get("description") or item.get("content") or item.get("title") or ""
            if desc:
                lines.append(f"- [{status}] {desc}" if status else f"- {desc}")
        elif isinstance(item, str) and item.strip():
            lines.append(f"- {item.strip()}")
    return "\n".join(lines)


def parse_gemini_session(
    session_payload: dict[str, Any],
    *,
    known_paths: set[str] | None = None,
) -> UnpackSession:
    """Parse raw Gemini CLI SessionPayload into an UnpackSession with turns T1..Tn."""
    agent = str(session_payload.get("agent") or "gemini-cli")
    file_name = str(session_payload.get("file_name") or "session.jsonl")
    raw_lines = session_payload.get("lines") or []
    paths_set = known_paths or set()

    meta, messages = replay_gemini_jsonl(raw_lines)
    raw_dirs = meta.get("directories")
    directories = [str(d) for d in raw_dirs if isinstance(d, str)] if isinstance(raw_dirs, list) else []

    turns: list[UnpackTurn] = []

    def add_turn(kind: str, **kwargs: Any) -> UnpackTurn:
        tid = f"T{len(turns) + 1}"
        turn = UnpackTurn(turn_id=tid, kind=kind, **kwargs)
        turns.append(turn)
        return turn

    for msg in messages:
        msg_type = str(msg.get("type") or "").lower()
        ts = str(msg.get("timestamp") or "")
        text = _extract_part_text(msg.get("content")).strip()

        if msg_type == "user":
            if text:
                add_turn("user", ts=ts, text=text)
            continue

        if msg_type in ("info", "error", "warning"):
            if text:
                add_turn("notice", ts=ts, text=text, level=msg_type)
            continue

        if msg_type == "gemini":
            thoughts = msg.get("thoughts")
            if isinstance(thoughts, list):
                for th in thoughts:
                    if not isinstance(th, dict):
                        continue
                    subj = str(th.get("subject") or "").strip()
                    desc = str(th.get("description") or "").strip()
                    th_ts = str(th.get("timestamp") or ts)
                    body = f"{subj}: {desc}" if subj and desc else (subj or desc)
                    if body:
                        add_turn("thought", ts=th_ts, text=body)

            if text:
                add_turn("assistant", ts=ts, text=text)

            tool_calls = msg.get("toolCalls")
            if isinstance(tool_calls, list):
                for tc in tool_calls:
                    if not isinstance(tc, dict):
                        continue
                    name = str(tc.get("name") or "")
                    args = tc.get("args") if isinstance(tc.get("args"), dict) else {}
                    status = str(tc.get("status") or "") or None
                    tc_ts = str(tc.get("timestamp") or ts)
                    result_text = _extract_part_text(tc.get("result")).strip()
                    result_display = tc.get("resultDisplay")

                    if name in EDIT_TOOL_NAMES:
                        raw_path = args.get("file_path") or args.get("path")
                        if not raw_path and isinstance(result_display, dict):
                            raw_path = result_display.get("filePath") or result_display.get("fileName")
                        rel_path = normalize_repo_path(
                            str(raw_path) if raw_path else None, directories, paths_set
                        )
                        instruction = (
                            str(args["instruction"]).strip()
                            if isinstance(args.get("instruction"), str) and args["instruction"].strip()
                            else None
                        )
                        orig: str | None = None
                        new: str | None = None
                        fdiff: str | None = None
                        is_new = False
                        if isinstance(result_display, dict):
                            if isinstance(result_display.get("originalContent"), str):
                                orig = result_display["originalContent"]
                            if isinstance(result_display.get("newContent"), str):
                                new = result_display["newContent"]
                            if isinstance(result_display.get("fileDiff"), str):
                                fdiff = result_display["fileDiff"]
                            is_new = bool(result_display.get("isNewFile", False))
                        add_turn(
                            "edit",
                            ts=tc_ts,
                            path=rel_path,
                            instruction=instruction,
                            status=status,
                            original_content=orig,
                            new_content=new,
                            file_diff=fdiff,
                            is_new_file=is_new,
                            tool_name=name,
                            text=instruction or (f"write_file {rel_path}" if rel_path else name),
                        )
                    elif name in SHELL_TOOL_NAMES:
                        cmd = str(args.get("command") or "").strip()
                        display_out = result_display if isinstance(result_display, str) else ""
                        output = result_text or display_out
                        exit_code = _parse_shell_exit_code(status, output)
                        add_turn(
                            "shell",
                            ts=tc_ts,
                            command=cmd,
                            exit_code=exit_code,
                            output=output,
                            status=status,
                            tool_name=name,
                            text=cmd,
                        )
                    elif name in READ_TOOL_NAMES:
                        target = (
                            args.get("file_path")
                            or args.get("path")
                            or args.get("pattern")
                            or args.get("dir_path")
                            or ""
                        )
                        rel = normalize_repo_path(str(target) if target else None, directories, paths_set)
                        summary = f"{name} {rel or target}".strip()
                        add_turn("read", ts=tc_ts, path=rel, tool_name=name, text=summary)
                    elif name in PLAN_TOOL_NAMES:
                        plan_text = _format_todos(args)
                        if plan_text:
                            add_turn("plan", ts=tc_ts, tool_name=name, text=plan_text)

    return UnpackSession(
        agent=agent,
        file_name=file_name,
        session_id=str(meta.get("sessionId") or ""),
        start_time=str(meta.get("startTime") or ""),
        last_updated=str(meta.get("lastUpdated") or ""),
        summary=str(meta["summary"]) if isinstance(meta.get("summary"), str) else None,
        directories=directories,
        turns=turns,
        turns_by_id={t.turn_id: t for t in turns},
    )
