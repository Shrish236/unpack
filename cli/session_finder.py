"""Locates and lightly trims Gemini CLI sessions on the developer machine."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TOOL_RESULT_MAX_BYTES = 20 * 1024
DROP_MESSAGE_KEYS = frozenset(
    {"tokens", "displayContent", "displayName", "renderOutputAsMarkdown"}
)
DROP_TOOL_KEYS = frozenset({"displayContent", "displayName", "renderOutputAsMarkdown"})


def _parse_iso_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def resolve_gemini_project_ids(
    repo_root: Path, gemini_dir: Path | None = None
) -> list[str]:
    """Resolve candidate Gemini CLI project folder IDs in priority order."""
    base_dir = gemini_dir or (Path.home() / ".gemini")
    projects_file = base_dir / "projects.json"

    real_root = os.path.realpath(str(repo_root))
    raw_root = str(repo_root)
    candidates: list[str] = []

    if projects_file.exists():
        try:
            data = json.loads(projects_file.read_text(encoding="utf-8"))
            projects = data.get("projects", {})
            if isinstance(projects, dict):
                for key in (real_root, raw_root):
                    val = projects.get(key)
                    if isinstance(val, str) and val and val not in candidates:
                        candidates.append(val)
        except Exception:
            pass

    for path_str in (real_root, raw_root):
        full_hash = hashlib.sha256(path_str.encode("utf-8")).hexdigest()
        for h in (full_hash, full_hash[:8]):
            if h not in candidates:
                candidates.append(h)

    return candidates


def get_session_last_updated(session_path: Path) -> datetime:
    """Return latest lastUpdated timestamp from header/$set records, falling back to mtime."""
    latest: datetime | None = None
    try:
        with session_path.open("r", encoding="utf-8", errors="replace") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(rec, dict):
                    continue
                if "lastUpdated" in rec:
                    ts = _parse_iso_timestamp(rec.get("lastUpdated"))
                    if ts is not None:
                        latest = ts
                set_payload = rec.get("$set")
                if isinstance(set_payload, dict) and "lastUpdated" in set_payload:
                    ts = _parse_iso_timestamp(set_payload.get("lastUpdated"))
                    if ts is not None:
                        latest = ts
    except OSError:
        pass

    if latest is not None:
        return latest
    return datetime.fromtimestamp(session_path.stat().st_mtime, tz=timezone.utc)


def find_gemini_session(
    repo_root: Path,
    *,
    after: datetime | None = None,
    gemini_dir: Path | None = None,
) -> Path | None:
    """Find the newest Gemini CLI session for repo_root updated on/after `after`."""
    base_dir = gemini_dir or (Path.home() / ".gemini")
    project_ids = resolve_gemini_project_ids(repo_root, gemini_dir=base_dir)

    if after is not None and after.tzinfo is None:
        after = after.replace(tzinfo=timezone.utc)

    matched: list[tuple[datetime, float, Path]] = []
    seen: set[Path] = set()

    for project_id in project_ids:
        chats_dir = base_dir / "tmp" / project_id / "chats"
        if not chats_dir.is_dir():
            continue
        for session_file in chats_dir.glob("session-*.jsonl"):
            if not session_file.is_file() or session_file in seen:
                continue
            seen.add(session_file)
            last_updated = get_session_last_updated(session_file)
            if after is not None and last_updated < after:
                continue
            matched.append((last_updated, session_file.stat().st_mtime, session_file))

    if not matched:
        return None

    matched.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return matched[0][2]


def get_gemini_cli_version(timeout_s: float = 1.0) -> str | None:
    """Return installed `gemini --version` output if quick and available, else None."""
    try:
        proc = subprocess.run(
            ["gemini", "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        if proc.returncode == 0:
            version = proc.stdout.strip().splitlines()[0].strip() if proc.stdout.strip() else ""
            return version or None
    except Exception:
        pass
    return None


def truncate_text(text: str, max_bytes: int = TOOL_RESULT_MAX_BYTES) -> str:
    """Cap a string at max_bytes (UTF-8), keeping head and tail with a truncation marker."""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text

    half = max(max_bytes // 2, 1)
    head = encoded[:half].decode("utf-8", errors="ignore")
    tail = encoded[-half:].decode("utf-8", errors="ignore")
    dropped = len(encoded) - (len(head.encode("utf-8")) + len(tail.encode("utf-8")))
    return f"{head}\n…[truncated {dropped} bytes]…\n{tail}"


def _is_file_diff(value: Any) -> bool:
    return isinstance(value, dict) and any(
        key in value for key in ("originalContent", "newContent", "fileDiff")
    )


def _trim_tool_result(value: Any, max_bytes: int) -> Any:
    """Cap tool call result strings while preserving JSON structure."""
    if isinstance(value, str):
        return truncate_text(value, max_bytes)
    if isinstance(value, list):
        return [_trim_tool_result(item, max_bytes) for item in value]
    if isinstance(value, dict):
        # Preserve embedded FileDiff structures intact if ever placed in result
        if _is_file_diff(value):
            return dict(value)
        return {k: _trim_tool_result(v, max_bytes) for k, v in value.items()}
    return value


def _trim_tool_call(tc: Any, max_bytes: int) -> Any:
    if not isinstance(tc, dict):
        return tc
    cleaned: dict[str, Any] = {}
    for key, val in tc.items():
        if key in DROP_TOOL_KEYS:
            continue
        if key == "result":
            cleaned[key] = _trim_tool_result(val, max_bytes)
        elif key == "resultDisplay":
            if _is_file_diff(val):
                cleaned[key] = dict(val)
            elif isinstance(val, str):
                cleaned[key] = truncate_text(val, max_bytes)
            else:
                cleaned[key] = val
        else:
            cleaned[key] = val
    return cleaned


def trim_session_line(
    record: dict[str, Any], max_bytes: int = TOOL_RESULT_MAX_BYTES
) -> dict[str, Any]:
    """Lightly trim a single Gemini CLI JSONL record per Section 3.3."""
    if "$patch" in record and isinstance(record["$patch"], dict):
        patch = dict(record["$patch"])
        for drop_key in DROP_MESSAGE_KEYS:
            patch.pop(drop_key, None)
        if isinstance(patch.get("toolCalls"), list):
            patch["toolCalls"] = [_trim_tool_call(tc, max_bytes) for tc in patch["toolCalls"]]
        if isinstance(patch.get("updates"), list):
            trimmed_updates = []
            for upd in patch["updates"]:
                if isinstance(upd, dict):
                    u = {k: v for k, v in upd.items() if k not in DROP_MESSAGE_KEYS}
                    if isinstance(u.get("toolCalls"), list):
                        u["toolCalls"] = [
                            _trim_tool_call(tc, max_bytes) for tc in u["toolCalls"]
                        ]
                    trimmed_updates.append(u)
                else:
                    trimmed_updates.append(upd)
            patch["updates"] = trimmed_updates
        return {"$patch": patch}

    cleaned: dict[str, Any] = {}
    for key, val in record.items():
        if key in DROP_MESSAGE_KEYS:
            continue
        if key == "toolCalls" and isinstance(val, list):
            cleaned[key] = [_trim_tool_call(tc, max_bytes) for tc in val]
        else:
            cleaned[key] = val
    return cleaned


def load_and_trim_session(
    session_path: Path,
    *,
    agent: str = "gemini-cli",
    agent_version: str | None = None,
    max_bytes: int = TOOL_RESULT_MAX_BYTES,
) -> dict[str, Any]:
    """Read a JSONL session file, trim noisy fields, and return a SessionPayload dict."""
    lines: list[dict[str, Any]] = []
    with session_path.open("r", encoding="utf-8", errors="replace") as fh:
        for raw_line in fh:
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                lines.append(trim_session_line(parsed, max_bytes=max_bytes))

    return {
        "agent": agent,
        "agent_version": agent_version,
        "file_name": session_path.name,
        "lines": lines,
    }
