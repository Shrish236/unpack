"""Edit-to-function mapping, provenance linking, test facts, and timeline (§4.4, §4.5)."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Any

from unpack_graph.extract import extract_file

from .changes import FuncChange
from .session import UnpackSession, UnpackTurn

_TEST_CMD_RE = re.compile(
    r"(?:^|[;&|]\s*)(?:(?:uv\s+run|poetry\s+run|pipenv\s+run)\s+)?"
    r"(?:(?:python3?(?:\.\d+)?)\s+-m\s+(?:pytest|unittest)\b|pytest\b|tox\b|nox\b|make\s+test\b)"
)
_PYTEST_SUMMARY_RE = re.compile(
    r"(\d+\s+(?:failed|passed|skipped|error|errors|xfailed|xpassed)"
    r"(?:,\s*\d+\s+(?:failed|passed|skipped|error|errors|xfailed|xpassed))*)"
)
_UNITTEST_RAN_RE = re.compile(r"Ran\s+(\d+)\s+tests?\s+in\s+[\d.]+s")
_UNITTEST_FAIL_RE = re.compile(r"FAILED\s*\(([^)]+)\)")


@dataclass
class EditTouch:
    """One function touched by a session edit (or synthetic out-of-band change)."""

    turn_id: str  # T# for edit/shell, or "outside_session"
    fn_id: str
    path: str
    kind: str  # added | deleted | modified
    logic_hash: str | None
    signature_hash: str | None
    text_hash: str | None
    body_hash: str | None
    is_out_of_band: bool = False
    diff_text: str = ""


@dataclass
class FunctionLink:
    """Complete provenance and edit history for one committed changed function."""

    fn_id: str
    change_kind: str  # added | deleted | functional | signature | text_only
    source: str  # session | session_then_formatted | session_partial | outside_session
    edit_turns: list[str] = field(default_factory=list)
    final_edit_turn: str | None = None
    out_of_band_turns: list[str] = field(default_factory=list)


@dataclass
class TestRunFact:
    __test__ = False
    turn: str
    command: str
    exit_code: int
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn": self.turn,
            "command": self.command,
            "exit_code": self.exit_code,
            "summary": self.summary,
        }


@dataclass
class LinkOutcome:
    links: dict[str, FunctionLink]
    sources: dict[str, str]
    last_test_run: TestRunFact | None
    tested_after_final_edit: bool
    last_edit_turn_id: str | None
    timeline: list[dict[str, Any]]
    reverted_functions: set[str]
    test_runs: list[TestRunFact]

    def facts_dict(self) -> dict[str, Any]:
        return {
            "last_test_run": self.last_test_run.to_dict() if self.last_test_run else None,
            "tested_after_final_edit": self.tested_after_final_edit,
        }


def _change_kind(ci: FuncChange) -> str:
    if ci.kind == "added":
        return "added"
    if ci.kind == "deleted":
        return "deleted"
    flags = set(ci.flags)
    if "signature" in flags:
        return "signature"
    if "functional" in flags:
        return "functional"
    return "text_only"


def _extract_funcs_map(path: str, content: str | None) -> dict[str, Any]:
    if not content:
        return {}
    try:
        mod = extract_file(path, content.encode("utf-8", errors="replace"))
    except Exception:
        return {}
    return {f.id: f for f in mod.funcs}


def _func_slice(lines: list[str], func: Any | None) -> list[str]:
    if func is None:
        return []
    start = max(0, func.start - 1)
    end = min(len(lines), func.end)
    return lines[start:end]


def _func_diff(
    path: str,
    before_content: str | None,
    after_content: str | None,
    before_func: Any | None,
    after_func: Any | None,
) -> str:
    b_lines = _func_slice((before_content or "").splitlines(), before_func)
    a_lines = _func_slice((after_content or "").splitlines(), after_func)
    diff_lines = list(
        difflib.unified_diff(
            b_lines,
            a_lines,
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            n=2,
            lineterm="",
        )
    )
    if not diff_lines:
        return ""
    return "\n".join(diff_lines)


def _diff_two_versions(
    path: str,
    before_content: str | None,
    after_content: str | None,
    *,
    turn_id: str,
    is_out_of_band: bool = False,
) -> list[EditTouch]:
    before_map = _extract_funcs_map(path, before_content)
    after_map = _extract_funcs_map(path, after_content)
    touches: list[EditTouch] = []

    for fid in sorted(set(before_map) | set(after_map)):
        bf = before_map.get(fid)
        af = after_map.get(fid)
        if bf is None and af is not None:
            touches.append(
                EditTouch(
                    turn_id=turn_id,
                    fn_id=fid,
                    path=path,
                    kind="added",
                    logic_hash=af.logic_hash,
                    signature_hash=af.signature_hash,
                    text_hash=af.text_hash,
                    body_hash=af.body_hash,
                    is_out_of_band=is_out_of_band,
                    diff_text=_func_diff(path, before_content, after_content, None, af),
                )
            )
        elif bf is not None and af is None:
            touches.append(
                EditTouch(
                    turn_id=turn_id,
                    fn_id=fid,
                    path=path,
                    kind="deleted",
                    logic_hash=None,
                    signature_hash=None,
                    text_hash=None,
                    body_hash=None,
                    is_out_of_band=is_out_of_band,
                    diff_text=_func_diff(path, before_content, after_content, bf, None),
                )
            )
        elif bf is not None and af is not None:
            if (
                bf.body_hash != af.body_hash
                or bf.text_hash != af.text_hash
                or bf.signature_hash != af.signature_hash
            ):
                touches.append(
                    EditTouch(
                        turn_id=turn_id,
                        fn_id=fid,
                        path=path,
                        kind="modified",
                        logic_hash=af.logic_hash,
                        signature_hash=af.signature_hash,
                        text_hash=af.text_hash,
                        body_hash=af.body_hash,
                        is_out_of_band=is_out_of_band,
                        diff_text=_func_diff(path, before_content, after_content, bf, af),
                    )
                )
    return touches


def is_test_command(command: str | None) -> bool:
    if not command:
        return False
    return bool(_TEST_CMD_RE.search(command.strip()))


def parse_test_run(turn: UnpackTurn) -> TestRunFact | None:
    """Deterministically extract a TestRunFact from a shell turn if it runs Python tests."""
    if turn.kind != "shell" or not is_test_command(turn.command):
        return None
    output = turn.output or ""
    summary = ""
    m = _PYTEST_SUMMARY_RE.findall(output)
    if m:
        summary = m[-1]
    else:
        um = _UNITTEST_RAN_RE.search(output)
        if um:
            count = um.group(1)
            fm = _UNITTEST_FAIL_RE.search(output)
            summary = f"Ran {count} tests - FAILED ({fm.group(1)})" if fm else f"Ran {count} tests - OK"

    exit_code = turn.exit_code
    if exit_code is None:
        lowered = output.lower()
        if "failed" in lowered or "traceback" in lowered or "error" in summary.lower():
            exit_code = 1
        else:
            exit_code = 0

    if not summary:
        summary = "passed" if exit_code == 0 else f"exit {exit_code}"

    return TestRunFact(
        turn=turn.turn_id,
        command=turn.command or "",
        exit_code=exit_code,
        summary=summary,
    )


def _turn_index(turn_id: str) -> int:
    try:
        return int(turn_id[1:]) if turn_id.startswith("T") else -1
    except ValueError:
        return -1


def _is_successful_edit(turn: UnpackTurn) -> bool:
    if turn.kind != "edit":
        return False
    if (turn.status or "").lower() in ("error", "failed", "cancelled", "canceled"):
        return False
    return turn.new_content is not None


def link_session_to_changes(
    session: UnpackSession,
    changes: list[FuncChange],
    base_graph: Any,
    head_graph: Any,
    changed_files: list[dict[str, Any]],
) -> LinkOutcome:
    """Map every session edit to functions, detect out-of-band edits, and compute facts/timeline."""
    changed_ids = {c.id for c in changes}
    head_contents = {
        f["path"]: f.get("head_content")
        for f in changed_files
        if isinstance(f.get("path"), str)
    }

    touches_by_fn: dict[str, list[EditTouch]] = {}
    touches_by_turn: dict[str, list[EditTouch]] = {}
    out_of_band_events: list[tuple[str, str, str, list[str]]] = []  # (turn_id, ts, path, fn_ids)

    # Track last seen new_content and turn index per Python file
    last_content_by_file: dict[str, tuple[str, int]] = {}  # path -> (content, turn_idx)
    all_shell_turns: list[tuple[int, UnpackTurn]] = []
    test_runs: list[TestRunFact] = []

    for idx, turn in enumerate(session.turns):
        if turn.kind == "shell":
            all_shell_turns.append((idx, turn))
            tr = parse_test_run(turn)
            if tr is not None:
                test_runs.append(tr)
            continue

        if not _is_successful_edit(turn) or not turn.path or not turn.path.endswith(".py"):
            continue

        path = turn.path
        orig = turn.original_content
        new = turn.new_content

        # Check for out-of-band change between previous edit and this edit
        if path in last_content_by_file:
            prev_content, prev_idx = last_content_by_file[path]
            if orig is not None and orig != prev_content:
                intervening = [s for si, s in all_shell_turns if prev_idx < si < idx]
                credit_turn = intervening[-1].turn_id if intervening else "outside_session"
                credit_ts = intervening[-1].ts if intervening else turn.ts
                oob_touches = _diff_two_versions(
                    path,
                    prev_content,
                    orig,
                    turn_id=credit_turn,
                    is_out_of_band=True,
                )
                for t in oob_touches:
                    touches_by_fn.setdefault(t.fn_id, []).append(t)
                if oob_touches:
                    out_of_band_events.append(
                        (credit_turn, credit_ts, path, [t.fn_id for t in oob_touches])
                    )

        edit_touches = _diff_two_versions(path, orig, new, turn_id=turn.turn_id, is_out_of_band=False)
        for t in edit_touches:
            touches_by_fn.setdefault(t.fn_id, []).append(t)
            touches_by_turn.setdefault(turn.turn_id, []).append(t)
            if t.diff_text:
                turn.function_diffs[t.fn_id] = t.diff_text

        if new is not None:
            last_content_by_file[path] = (new, idx)

    # Check for out-of-band change AFTER the last edit to each file vs committed head_content
    for path, (last_content, last_idx) in last_content_by_file.items():
        committed = head_contents.get(path)
        if committed is not None and committed != last_content:
            trailing_shells = [s for si, s in all_shell_turns if si > last_idx]
            credit_turn = trailing_shells[-1].turn_id if trailing_shells else "outside_session"
            credit_ts = trailing_shells[-1].ts if trailing_shells else session.last_updated
            oob_touches = _diff_two_versions(
                path,
                last_content,
                committed,
                turn_id=credit_turn,
                is_out_of_band=True,
            )
            for t in oob_touches:
                touches_by_fn.setdefault(t.fn_id, []).append(t)
            if oob_touches:
                out_of_band_events.append(
                    (credit_turn, credit_ts, path, [t.fn_id for t in oob_touches])
                )

    # Link every committed changed function to its session edits and classify provenance
    links: dict[str, FunctionLink] = {}
    sources: dict[str, str] = {}
    latest_final_edit_idx = -1
    latest_final_edit_turn: str | None = None

    for ch in changes:
        ckind = _change_kind(ch)
        all_touches = touches_by_fn.get(ch.id, [])
        session_touches = [t for t in all_touches if not t.is_out_of_band]
        oob_turns = [t.turn_id for t in all_touches if t.is_out_of_band]
        edit_turn_ids = list(dict.fromkeys(t.turn_id for t in session_touches))

        if not session_touches:
            source = "outside_session"
            final_turn = None
        elif ch.kind == "deleted":
            final_del = next((t for t in reversed(session_touches) if t.kind == "deleted"), None)
            if final_del is not None:
                source = "session"
                final_turn = final_del.turn_id
            else:
                source = "session_partial"
                final_turn = None
        else:
            head_func = head_graph.funcs.get(ch.id)
            if head_func is None:
                source = "session_partial"
                final_turn = None
            else:
                matching = [
                    t
                    for t in session_touches
                    if t.logic_hash == head_func.logic_hash
                    and t.signature_hash == head_func.signature_hash
                ]
                if matching:
                    final = matching[-1]
                    final_turn = final.turn_id
                    if final.text_hash == head_func.text_hash and final.body_hash == head_func.body_hash:
                        source = "session"
                    else:
                        source = "session_then_formatted"
                else:
                    source = "session_partial"
                    final_turn = None

        if final_turn is not None:
            ti = _turn_index(final_turn)
            if ti > latest_final_edit_idx:
                latest_final_edit_idx = ti
                latest_final_edit_turn = final_turn

        links[ch.id] = FunctionLink(
            fn_id=ch.id,
            change_kind=ckind,
            source=source,
            edit_turns=edit_turn_ids,
            final_edit_turn=final_turn,
            out_of_band_turns=oob_turns,
        )
        sources[ch.id] = source

    # Fallback last_edit_turn if there were session edits (even partial)
    if latest_final_edit_turn is None:
        for turn in reversed(session.turns):
            if _is_successful_edit(turn):
                latest_final_edit_turn = turn.turn_id
                latest_final_edit_idx = _turn_index(turn.turn_id)
                break

    last_test_run = test_runs[-1] if test_runs else None
    tested_after_final_edit = bool(
        last_test_run is not None
        and latest_final_edit_idx >= 0
        and _turn_index(last_test_run.turn) > latest_final_edit_idx
    )

    # Identify reverted functions (touched in session edits, absent from final diff)
    reverted_functions = {
        fid
        for fid, tlist in touches_by_fn.items()
        if fid not in changed_ids and any(not t.is_out_of_band for t in tlist)
    }

    # Build TimelineTurn entries matching server/app/schemas/api.py
    timeline: list[dict[str, Any]] = []
    test_by_turn = {tr.turn: tr for tr in test_runs}
    oob_by_turn: dict[str, list[tuple[str, list[str]]]] = {}
    for oob_tid, _oob_ts, oob_path, oob_fns in out_of_band_events:
        oob_by_turn.setdefault(oob_tid, []).append((oob_path, oob_fns))

    for turn in session.turns:
        if turn.kind == "user":
            label = turn.text.splitlines()[0][:120]
            timeline.append(
                {
                    "turn": turn.turn_id,
                    "kind": "user_request",
                    "ts": turn.ts,
                    "label": label,
                    "nodes": [],
                    "reverted": False,
                    "exit_code": None,
                    "finding_id": None,
                }
            )
        elif turn.kind == "edit" and _is_successful_edit(turn):
            touched = touches_by_turn.get(turn.turn_id, [])
            touched_ids = list(dict.fromkeys(t.fn_id for t in touched))
            is_reverted = bool(touched_ids) and all(fid not in changed_ids for fid in touched_ids)
            label = turn.path or turn.tool_name or "edit"
            timeline.append(
                {
                    "turn": turn.turn_id,
                    "kind": "edit",
                    "ts": turn.ts,
                    "label": label,
                    "nodes": touched_ids,
                    "reverted": is_reverted,
                    "exit_code": None,
                    "finding_id": None,
                }
            )
        elif turn.kind == "shell":
            if turn.turn_id in test_by_turn:
                tr = test_by_turn[turn.turn_id]
                timeline.append(
                    {
                        "turn": turn.turn_id,
                        "kind": "test_run",
                        "ts": turn.ts,
                        "label": f"{tr.command[:60]}: {tr.summary}",
                        "nodes": [],
                        "reverted": False,
                        "exit_code": tr.exit_code,
                        "finding_id": None,
                    }
                )
            elif turn.turn_id in oob_by_turn:
                oob_nodes = sorted(
                    {fid for _p, fids in oob_by_turn[turn.turn_id] for fid in fids}
                )
                timeline.append(
                    {
                        "turn": turn.turn_id,
                        "kind": "out_of_band",
                        "ts": turn.ts,
                        "label": (turn.command or "shell edit")[:100],
                        "nodes": oob_nodes,
                        "reverted": False,
                        "exit_code": turn.exit_code,
                        "finding_id": None,
                    }
                )

    # Record any uncredited outside_session edits at the end of timeline
    if "outside_session" in oob_by_turn:
        oob_nodes = sorted({fid for _p, fids in oob_by_turn["outside_session"] for fid in fids})
        timeline.append(
            {
                "turn": "outside_session",
                "kind": "out_of_band",
                "ts": session.last_updated,
                "label": "Edited outside the agent session",
                "nodes": oob_nodes,
                "reverted": False,
                "exit_code": None,
                "finding_id": None,
            }
        )

    return LinkOutcome(
        links=links,
        sources=sources,
        last_test_run=last_test_run,
        tested_after_final_edit=tested_after_final_edit,
        last_edit_turn_id=latest_final_edit_turn,
        timeline=timeline,
        reverted_functions=reverted_functions,
        test_runs=test_runs,
    )
