"""Claude Code transcript -> Gemini CLI session format.

The server reads one session format (Gemini CLI JSONL, server design D8). Everything specific to
Claude Code stays here: its record shapes, its tool names, and the fact that an Edit result does
not carry the whole file. Edits are replayed against the file as it was at the base commit, so each
converted edit has the exact `originalContent` and `newContent` the server's edit linker needs.

Only `.py` files get full contents, because the server's code graph is Python only. Other files
keep a small unified diff, so the timeline still shows them without bloating the payload.
"""

from __future__ import annotations

import difflib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

_TAGS = re.compile(
    r"<(system-reminder|ide_opened_file|ide_selection|command-[a-z-]+|local-command-[a-z-]+|task-notification)\b[^>]*>.*?</\1>",
    re.S,
)
_SKIP_PREFIXES = ("[SYSTEM NOTIFICATION", "Caveat:", "[Request interrupted")
_READ_TOOLS = {"Read": "read_file", "Grep": "grep", "Glob": "glob", "LS": "list_directory"}
_CODE_SUFFIXES = {".py"}


def is_claude_code_transcript(path: Path, peek: int = 60) -> bool:
    """True when the file looks like a Claude Code transcript (records with `message` and `sessionId`)."""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh):
                if i >= peek:
                    break
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(rec, dict) and rec.get("type") in ("user", "assistant") and "message" in rec and "sessionId" in rec:
                    return True
    except OSError:
        return False
    return False


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _human_text(content: Any) -> str:
    text = _TAGS.sub("", _text_of(content)).strip()
    return "" if text.startswith(_SKIP_PREFIXES) else text


def _git_show(repo: Path | None, ref: str | None, rel: str) -> str | None:
    if repo is None or not ref:
        return None
    out = subprocess.run(["git", "-C", str(repo), "show", f"{ref}:{rel}"], capture_output=True, text=True)
    return out.stdout if out.returncode == 0 else None


def _unified(old: str | None, new: str | None, name: str) -> str:
    a = (old or "").splitlines(keepends=True)
    b = (new or "").splitlines(keepends=True)
    return "".join(difflib.unified_diff(a, b, f"a/{name}", f"b/{name}", n=3))


_HEREDOC = re.compile(r"cat\s*>\s*(\S+)\s*<<\s*['\"]?(\w+)['\"]?[ \t]*\n(.*?)\n\2[ \t]*(?:\n|$)", re.S)
_CD = re.compile(r"^\s*cd\s+(\S+)\s*&&")


def _heredoc_writes(command: str, repo: Path | None) -> list[tuple[str, str]]:
    """Files a shell command writes with `cat > file <<'EOF'`, as (absolute path, content).

    Claude Code often writes files this way instead of with its Write tool. Relative paths are
    resolved against a leading `cd DIR &&`, else the repository root. Appends (`>>`) are ignored.
    """
    cd = _CD.match(command)
    base = Path(cd.group(1)).expanduser() if cd else None
    if base is not None and not base.is_absolute() and repo is not None:
        base = repo / base
    root = base or repo
    out: list[tuple[str, str]] = []
    for m in _HEREDOC.finditer(command):
        path = Path(m.group(1)).expanduser()
        if not path.is_absolute():
            if root is None:
                continue
            path = root / path
        out.append((str(path), m.group(3) + "\n"))
    return out


def _tool_result_text(block: dict[str, Any]) -> str:
    c = block.get("content")
    return c if isinstance(c, str) else _text_of(c)


class _Files:
    """File contents as the agent saw them: base commit, then every edit applied in order."""

    def __init__(self, repo: Path | None, base: str | None) -> None:
        self.repo, self.base = repo, base
        self.state: dict[str, str | None] = {}

    def _rel(self, path: str) -> str:
        p = Path(path)
        if self.repo is not None:
            try:
                return str(p.resolve().relative_to(self.repo.resolve()))
            except (ValueError, OSError):
                pass
        return str(p)

    def current(self, path: str) -> str | None:
        if path not in self.state:
            self.state[path] = _git_show(self.repo, self.base, self._rel(path))
        return self.state[path]


def convert_claude_code(path: Path, *, repo_root: Path | None = None, base_sha: str | None = None) -> list[dict[str, Any]]:
    """Return Gemini-format JSONL records for a Claude Code transcript.

    `repo_root` and `base_sha` let edits start from the file as it was at the base commit.
    """
    files = _Files(repo_root, base_sha)
    out: list[dict[str, Any]] = []
    calls: dict[str, dict[str, Any]] = {}   # tool_use id -> the toolCall dict, to attach its result later
    undo: dict[str, tuple[str, str | None]] = {}  # tool_use id -> (path, state before), restored if the edit failed
    cwd, first_ts, last_ts, n = None, None, None, 0
    last_said = ""

    for raw in path.open("r", encoding="utf-8", errors="replace"):
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(rec, dict) or rec.get("isSidechain") or rec.get("isMeta"):
            continue
        kind, msg, ts = rec.get("type"), rec.get("message"), str(rec.get("timestamp") or "")
        if kind not in ("user", "assistant") or not isinstance(msg, dict):
            continue
        cwd = cwd or rec.get("cwd")
        first_ts, last_ts = first_ts or ts, ts or last_ts
        content = msg.get("content")

        if kind == "user":
            blocks = content if isinstance(content, list) else []
            for b in blocks:  # tool results belong to the call they answer
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    tc = calls.get(str(b.get("tool_use_id")))
                    if tc is None:
                        continue
                    text, failed = _tool_result_text(b), bool(b.get("is_error"))
                    tc["status"] = "error" if failed else "success"
                    if tc["name"] == "run_shell_command":
                        tc["result"], tc["resultDisplay"] = text, text
                    elif failed and (u := undo.get(str(b.get("tool_use_id")))):
                        files.state[u[0]] = u[1]
                        tc.pop("resultDisplay", None)
            text = _human_text(content)
            if text:
                n += 1
                out.append({"id": f"m{n}", "timestamp": ts, "type": "user", "content": [{"text": text}]})
            continue

        # assistant
        blocks = content if isinstance(content, list) else []
        text = _text_of(blocks).strip()
        thoughts = [
            {"subject": "", "description": b["thinking"].strip(), "timestamp": ts}
            for b in blocks if isinstance(b, dict) and b.get("type") == "thinking" and str(b.get("thinking") or "").strip()
        ]
        if text:
            last_said = text
        tool_calls: list[dict[str, Any]] = []
        for b in blocks:
            if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                continue
            tc = _convert_tool(b, ts, files, last_said, undo)
            for one in tc:
                tool_calls.append(one)
                calls[str(one["id"])] = one
        if not (text or thoughts or tool_calls):
            continue
        n += 1
        m: dict[str, Any] = {"id": f"m{n}", "timestamp": ts, "type": "gemini", "content": [{"text": text}] if text else []}
        if thoughts:
            m["thoughts"] = thoughts
        if tool_calls:
            m["toolCalls"] = tool_calls
        if rec.get("message", {}).get("model"):
            m["model"] = rec["message"]["model"]
        out.append(m)

    header = {
        "sessionId": next((json.loads(l).get("sessionId") for l in path.open() if '"sessionId"' in l), path.stem),
        "projectHash": "claude-code", "startTime": first_ts or "", "lastUpdated": last_ts or "", "kind": "main",
        "directories": [str(repo_root or cwd or "")],
    }
    return [header, *out]


def _convert_tool(b: dict[str, Any], ts: str, files: _Files, said: str, undo: dict[str, tuple[str, str | None]]) -> list[dict[str, Any]]:
    name, args, tid = str(b.get("name")), b.get("input") if isinstance(b.get("input"), dict) else {}, str(b.get("id"))
    base = {"timestamp": ts, "status": "success"}
    if name in ("Edit", "MultiEdit", "Write"):
        path = str(args.get("file_path") or "")
        pairs = (
            [(args.get("old_string"), args.get("new_string"), bool(args.get("replace_all")))] if name == "Edit"
            else [(e.get("old_string"), e.get("new_string"), bool(e.get("replace_all"))) for e in args.get("edits", []) if isinstance(e, dict)]
            if name == "MultiEdit" else []
        )
        instruction = (said.splitlines()[0] if said else f"Edit {Path(path).name}")[:240]
        code = Path(path).suffix in _CODE_SUFFIXES
        before = files.current(path) if code else None
        after = before
        if name == "Write":
            after = str(args.get("content") or "")
        else:
            for old, new, every in pairs:
                if isinstance(old, str) and isinstance(new, str):
                    if code and after is not None and old in after:
                        after = after.replace(old, new) if every else after.replace(old, new, 1)
                    elif code:
                        after = None  # the file moved under us: keep the edit, drop the contents
                        break
        shown_old = before if name == "Write" else (pairs[0][0] if pairs else "")
        shown_new = after if name == "Write" else (pairs[0][1] if pairs else "")
        display: dict[str, Any] = {
            "fileName": Path(path).name, "filePath": path, "isNewFile": name == "Write" and before is None,
            "fileDiff": _unified(shown_old if isinstance(shown_old, str) else "", shown_new if isinstance(shown_new, str) else "", Path(path).name),
        }
        if code and after is not None:
            display["originalContent"], display["newContent"] = before, after
            undo[tid] = (path, before)
            files.state[path] = after
        tool = "write_file" if name == "Write" else "replace"
        a: dict[str, Any] = {"file_path": path}
        if name == "Write":
            a["content"] = str(args.get("content") or "")[:2000] if not code else str(args.get("content") or "")
        else:
            a["instruction"] = instruction
        return [{"id": tid, "name": tool, "args": a, "resultDisplay": display, **base}]
    if name == "Bash":
        command = str(args.get("command") or "")
        writes = [
            _convert_tool(
                {"name": "Write", "id": f"{tid}-w{i}", "input": {"file_path": path, "content": body}}, ts, files, said, undo
            )[0]
            for i, (path, body) in enumerate(_heredoc_writes(command, files.repo), 1)
        ]
        # The files are written by the command, so their write turns come first and the command turn follows.
        return [*writes, {"id": tid, "name": "run_shell_command", "args": {"command": command}, **base}]
    if name in _READ_TOOLS:
        return [{"id": tid, "name": _READ_TOOLS[name], "args": {k: v for k, v in args.items() if k in ("file_path", "path", "pattern")}, **base}]
    if name == "TodoWrite":
        todos = [{"description": t.get("content", ""), "status": t.get("status", "")} for t in args.get("todos", []) if isinstance(t, dict)]
        return [{"id": tid, "name": "write_todos", "args": {"todos": todos}, **base}]
    return []  # Agent, Skill, ToolSearch, Artifact, WebFetch...: not part of the decision record
