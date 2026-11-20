"""Build trimmed LLM input prompt from UnpackSession, edit links, and computed FACTS (§4.6)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import settings
from .graph_context import build_code_context
from .prompt_text import labels_line, reasons_prompt, repair_prompt, response_section
from ..pipeline.edit_linker import LinkOutcome
from ..pipeline.session import UnpackSession, UnpackTurn

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
_IMPORTANT_SHELL_RE = re.compile(r"FAILED|Error|Traceback|assert|passed|failed")


@dataclass
class BuiltPrompt:
    system_prompt: str
    user_prompt: str
    alias_to_node: dict[str, str]  # F1 -> path::Qual.Name
    node_to_alias: dict[str, str]  # path::Qual.Name -> F1
    target_node_ids: list[str]  # non-text_only nodes sent to LLM
    text_only_node_ids: list[str]  # auto-labelled locally, skipped by LLM
    overflow_node_ids: list[str] = field(default_factory=list)  # past MAX_LLM_FUNCTIONS, not sent to the model


def load_system_prompt(version: int = 1) -> str:
    return reasons_prompt(version)


def load_repair_prompt(version: int = 1, schema: type | None = None) -> str:  # version is kept for callers that pass it
    return repair_prompt(schema)


def trim_shell_output(output: str, head_lines: int = 40, tail_lines: int = 60) -> str:
    """Keep first 40 lines, last 60 lines, and any diagnostic/test-result lines in between."""
    lines = output.splitlines()
    if len(lines) <= head_lines + tail_lines:
        return output

    keep_indices: set[int] = set(range(head_lines))
    keep_indices.update(range(len(lines) - tail_lines, len(lines)))
    for idx in range(head_lines, len(lines) - tail_lines):
        if _IMPORTANT_SHELL_RE.search(lines[idx]):
            keep_indices.add(idx)

    out: list[str] = []
    prev = -1
    for idx in sorted(keep_indices):
        if prev != -1 and idx > prev + 1:
            out.append(f"... [{idx - prev - 1} lines omitted] ...")
        out.append(lines[idx])
        prev = idx
    return "\n".join(out)


def _format_turn_for_llm(turn: UnpackTurn) -> str | None:
    if turn.kind == "user":
        return f"[{turn.turn_id}] user: {turn.text}"
    if turn.kind == "assistant":
        return f"[{turn.turn_id}] assistant: {turn.text}"
    if turn.kind == "thought":
        return f"[{turn.turn_id}] thought: {turn.text}"
    if turn.kind == "plan":
        return f"[{turn.turn_id}] plan:\n{turn.text}"
    if turn.kind == "read":
        return f"[{turn.turn_id}] read: {turn.text or turn.path or ''}".strip()
    if turn.kind == "notice":
        if (turn.level or "").lower() != "error":
            return None
        return f"[{turn.turn_id}] error: {turn.text}"
    if turn.kind == "shell":
        status_part = f" -> exit {turn.exit_code}" if turn.exit_code is not None else ""
        header = f"[{turn.turn_id}] shell: {turn.command or ''}{status_part}"
        if turn.output:
            trimmed = trim_shell_output(turn.output)
            return f"{header}\n      output:\n{trimmed}"
        return header
    if turn.kind == "edit":
        parts = [f"[{turn.turn_id}] edit {turn.path or '(unknown)'}"]
        if turn.instruction:
            parts[0] += f'  instruction: "{turn.instruction}"'
        if turn.status and turn.status.lower() not in ("success", "succeeded", "ok", "completed"):
            parts[0] += f"  status: {turn.status}"
        if turn.function_diffs:
            for fn_id, fdiff in turn.function_diffs.items():
                parts.append(f"      function {fn_id}:\n{fdiff}")
        elif turn.file_diff:
            # Cap non-Python or fallback file diff concisely
            diff_preview = turn.file_diff[:4000]
            parts.append(f"      diff:\n{diff_preview}")
        return "\n".join(parts)
    return None


def build_reasoning_prompt(
    session: UnpackSession,
    link_outcome: LinkOutcome,
    graph_nodes: list[dict[str, Any]],
    reading_order: list[str],
    *,
    prompt_version: int = 1,
    max_functions: int | None = None,
    graph: Any | None = None,
) -> BuiltPrompt:
    """Build the single-call LLM prompt containing TASK, CHANGED FUNCTIONS, FACTS, and SESSION."""
    limit = max_functions or settings.MAX_LLM_FUNCTIONS
    nodes_by_id = {n["id"]: n for n in graph_nodes}

    # Preserve reading_order, falling back to link_outcome order for any remaining functions
    ordered_ids = [nid for nid in reading_order if nid in link_outcome.links]
    for nid in link_outcome.links:
        if nid not in ordered_ids:
            ordered_ids.append(nid)

    text_only_ids: list[str] = []
    target_ids: list[str] = []
    overflow_ids: list[str] = []
    for nid in ordered_ids:
        link = link_outcome.links[nid]
        if link.change_kind == "text_only":
            text_only_ids.append(nid)
        elif len(target_ids) < limit:
            target_ids.append(nid)
        else:
            overflow_ids.append(nid)

    alias_to_node: dict[str, str] = {}
    node_to_alias: dict[str, str] = {}
    for idx, nid in enumerate(target_ids, start=1):
        alias = f"F{idx}"
        alias_to_node[alias] = nid
        node_to_alias[nid] = alias

    sections: list[str] = []

    # 1. TASK
    user_turns = [t for t in session.turns if t.kind == "user"]
    task_lines = ["## TASK"]
    if user_turns:
        for ut in user_turns:
            task_lines.append(f"[{ut.turn_id}] {ut.text}")
    else:
        task_lines.append("(no user messages recorded)")
    sections.append("\n".join(task_lines))

    # 2. CHANGED FUNCTIONS
    fn_lines = ["## CHANGED FUNCTIONS"]
    for alias, nid in alias_to_node.items():
        link = link_outcome.links[nid]
        fn_lines.append(f"{alias} {nid}  ({link.change_kind}, source: {link.source})")
        if link.edit_turns:
            formatted_edits = [
                f"{tid} (final)" if tid == link.final_edit_turn else tid for tid in link.edit_turns
            ]
            fn_lines.append(f"   edits: {', '.join(formatted_edits)}")
        if link.out_of_band_turns:
            fn_lines.append(f"   out_of_band: {', '.join(link.out_of_band_turns)}")
    sections.append("\n".join(fn_lines))

    # 2b. CODE CONTEXT from the head code graph (callers, callees, test reach). Context only, never evidence.
    if graph is not None and settings.GRAPH_CONTEXT_ENABLED and target_ids:
        sections.append(build_code_context(graph, target_ids, node_to_alias))

    # 3. FACTS (computed, do not contradict)
    fact_lines = ["## FACTS (computed, do not contradict)"]
    if link_outcome.last_test_run:
        tr = link_outcome.last_test_run
        fact_lines.append(
            f'- Last test run: {tr.turn} `{tr.command}` -> exit {tr.exit_code}, "{tr.summary}"'
        )
    else:
        fact_lines.append("- Last test run: none")

    if link_outcome.last_edit_turn_id:
        no_test_after = "false" if link_outcome.tested_after_final_edit else "true"
        fact_lines.append(
            f"- No test run after final edit {link_outcome.last_edit_turn_id}? -> {no_test_after}"
        )
    else:
        fact_lines.append("- No test run after final edit? -> unknown (no session edits)")

    for alias, nid in alias_to_node.items():
        node = nodes_by_id.get(nid)
        test_info = (node or {}).get("test")
        if test_info is None:
            continue
        label = test_info.get("label", "none")
        count = test_info.get("count", 0)
        if label == "none":
            fact_lines.append(f"- Tests that reach {alias} ({nid}): none (from code graph)")
        else:
            fact_lines.append(
                f"- Tests that reach {alias} ({nid}): {label} ({count} test(s), from code graph)"
            )
    sections.append("\n".join(fact_lines))

    # 4. SESSION
    sess_lines = ["## SESSION"]
    for turn in session.turns:
        rendered = _format_turn_for_llm(turn)
        if rendered:
            sess_lines.append(rendered)
    sections.append("\n".join(sess_lines))

    # 5. RESPONSE: last, so it is the freshest thing the model reads
    turn_ids = [t.turn_id for t in session.turns]
    sections.append(response_section([
        'Reply with one JSON object with the keys "summary", "functions" and "session_review", as described in the system prompt.',
        f'"functions" must have exactly one item for each of these labels: {labels_line(list(alias_to_node))}. One item per label: none missing, none extra.',
        f'The turns in this session run up to {turn_ids[-1] if turn_ids else "none"}; every "turn" you give must be one of them.',
        "Quote only from ## SESSION, copied exactly. Do not quote ## CODE CONTEXT or ## FACTS.",
    ]))

    return BuiltPrompt(
        system_prompt=load_system_prompt(prompt_version),
        user_prompt="\n\n".join(sections),
        alias_to_node=alias_to_node,
        node_to_alias=node_to_alias,
        target_node_ids=target_ids,
        text_only_node_ids=text_only_ids,
        overflow_node_ids=overflow_ids,
    )
