"""Decision extraction: what was decided, by whom, and whether the steering was followed.

Deterministic part: tool calls the human refused become `permission_denied` decisions straight from the
session. LLM part: the rest, extracted with a structured prompt, then every quote is checked against the
session text. A decision whose quote is not in the session is dropped and counted, never shown.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..config import settings
from ..llm.budget import LLMBudget
from ..llm.client import LLMCallRecord, LLMDecisionOutput, run_structured_llm
from ..llm.prompt_builder import _format_turn_for_llm
from ..llm.prompt_text import decisions_prompt, labels_line, response_section
from .session import UnpackSession
from .steering import SteeringSnapshot
from .verify import quote_matches_turn

DECISIONS_PROMPT_VERSION = 4
AGENT_TURN_KINDS = {"assistant", "thought", "plan", "edit", "shell"}
_DEP_CMD_RE = re.compile(
    r"(?i)\b(pip3? install|npm (i|install|add)|yarn add|pnpm add|poetry add|cargo add|go get|apt(-get)? install)\b"
)


@dataclass
class DecisionResult:
    decisions: list[dict[str, Any]] = field(default_factory=list)
    highlights: list[dict[str, Any]] = field(default_factory=list)
    rejected_count: int = 0
    llm_calls: list[LLMCallRecord] = field(default_factory=list)
    model: str | None = None
    error: str | None = None


def denied_decisions(signals: dict[str, Any]) -> list[dict[str, Any]]:
    """A refused tool call is a human decision we can state without a model."""
    out = []
    for d in signals.get("denied", []):
        target = d.get("target", "")
        dep = bool(_DEP_CMD_RE.search(target))
        out.append({
            "turn": d["turn"], "actor": "human", "kind": "permission_denied",
            "type": "dependency" if dep else "other",
            "proposal": f"The agent asked to run {d.get('tool')}: {target}"[:300],
            "choice": "The human refused the tool call",
            "statement": "Do not add a new runtime dependency without approval" if dep else "",
            "quote": target, "rule_id": None, "rule_followed": None,
            "source": "parsed", "verified": True,
        })
    return out


_CODE_CONTEXT_ID = re.compile(r"^\S+ (\S+::\S+)$")


def build_decision_prompt(
    session: UnpackSession, steering: SteeringSnapshot, signals: dict[str, Any], code_context: str | None = None,
) -> tuple[str, str]:
    system = decisions_prompt(DECISIONS_PROMPT_VERSION)
    sections = ["## TASK"]
    users = [t for t in session.turns if t.kind == "user"]
    sections += [f"[{t.turn_id}] {t.text}" for t in users] or ["(no user messages recorded)"]

    sections.append("\n## STEERING")
    if steering.rules:
        sections += [f"{r.id} ({r.source}, {r.section}): {r.text}" for r in steering.rules]
    else:
        sections.append("(no steering files found in the repo)")

    sections.append("\n## REFUSED TOOL CALLS")
    denied = signals.get("denied", [])
    sections += [f"[{d['turn']}] {d['tool']}: {d['target']}" for d in denied] or ["(none)"]

    if code_context:
        # build_code_context starts with its own heading line; this section has its own, so drop it
        body = code_context.splitlines()
        if body and body[0].startswith("## "):
            body = body[1:]
        sections.append("\n## CHANGED CODE (from the code graph at the pushed commit. Context only: never quote it as evidence)\n" + "\n".join(body))
    flags = [f"{f['flag']} ({f.get('path') or 'n/a'})" for f in signals.get("flags", [])]
    sections.append(
        "\n## SIGNALS\n"
        f"- attempts: {signals.get('attempts', 1)}; shell failures: {signals.get('shell_failures', 0)}; edits: {signals.get('edits', 0)}\n"
        f"- flags: {', '.join(flags) or 'none'}"
    )

    sections.append("\n## SESSION")
    for turn in session.turns:
        rendered = _format_turn_for_llm(turn)
        if rendered:
            sections.append(rendered)

    node_ids = [m.group(1) for line in (code_context or "").splitlines() if (m := _CODE_CONTEXT_ID.match(line))]
    user_turns = [t.turn_id for t in users]
    sections.append("")
    sections.append(response_section([
        'Reply with one JSON object with the keys "decisions" and "highlights", as described in the system prompt.',
        f"Steering rule ids you may use: {labels_line([r.id for r in steering.rules])} (use null when no rule applies).",
        f'Function ids you may use in "nodes": {labels_line(node_ids)} (use [] when none).',
        f"The turns in this session run up to {session.turns[-1].turn_id if session.turns else 'none'}. Human decisions must be on a user turn: {labels_line(user_turns)}.",
        "Do not list the refused tool calls. Quote only from ## SESSION, copied exactly.",
    ]))
    return system, "\n".join(sections)


def _valid_nodes(ids: list[str], known: set[str]) -> list[str]:
    """Only ids that are really in the graph, each once. A made-up id is dropped, the decision is kept."""
    out: list[str] = []
    for i in ids:
        if i in known and i not in out:
            out.append(i)
    return out


def verify_decisions(
    output: LLMDecisionOutput, session: UnpackSession, steering: SteeringSnapshot, known_nodes: set[str] | None = None,
) -> DecisionResult:
    rule_ids = {r.id for r in steering.rules}
    known = known_nodes or set()
    result = DecisionResult()
    for d in output.decisions:
        turn = session.turns_by_id.get(d.turn)
        ok = turn is not None and bool(d.quote) and quote_matches_turn(session, d.turn, d.quote)
        if ok and d.actor == "human":
            ok = turn.kind == "user" and d.kind != "choice"
        if ok and d.actor == "agent":
            ok = turn.kind in AGENT_TURN_KINDS
        if not ok:
            result.rejected_count += 1
            continue
        rule_id = d.rule_id if d.rule_id in rule_ids else None
        result.decisions.append({
            "turn": d.turn, "actor": d.actor, "kind": d.kind, "type": d.type,
            "proposal": d.proposal[:400], "choice": d.choice[:400],
            "statement": d.statement[:300] if d.actor == "human" else "",
            "quote": d.quote[:600], "rule_id": rule_id,
            "rule_followed": d.rule_followed if rule_id else None,
            "nodes": _valid_nodes(d.nodes, known),
            "source": "llm", "verified": True,
        })
    for h in output.highlights[:4]:
        if h.turn in session.turns_by_id and (not h.quote or quote_matches_turn(session, h.turn, h.quote)):
            result.highlights.append({"kind": h.kind, "text": h.text[:300], "turn": h.turn, "quote": h.quote[:400],
                                      "nodes": _valid_nodes(h.nodes, known)})
        else:
            result.rejected_count += 1
    return result


async def extract_decisions(
    session: UnpackSession, steering: SteeringSnapshot, signals: dict[str, Any], *, daily_tokens_used: int = 0,
    code_context: str | None = None, budget: LLMBudget | None = None, known_nodes: set[str] | None = None,
) -> DecisionResult:
    """Parsed decisions always; LLM decisions when reasoning is enabled and the call succeeds."""
    parsed = denied_decisions(signals)
    if not settings.REASONING_ENABLED:
        return DecisionResult(decisions=parsed, error="reasoning disabled")
    if budget is not None and budget.exhausted():
        return DecisionResult(decisions=parsed, error=budget.reason())
    system, user = build_decision_prompt(session, steering, signals, code_context)
    res = await run_structured_llm(
        system_prompt=system, user_prompt=user, schema=LLMDecisionOutput, purpose="decisions",
        prompt_version=DECISIONS_PROMPT_VERSION, daily_tokens_used=budget.used if budget else daily_tokens_used,
    )
    if budget is not None:
        budget.record(res)
    if res.output is None:
        return DecisionResult(decisions=parsed, llm_calls=res.calls, error=res.error)
    verified = verify_decisions(res.output, session, steering, known_nodes)
    verified.decisions = sorted(parsed + verified.decisions, key=lambda d: int(d["turn"][1:]))
    verified.llm_calls = res.calls
    verified.model = res.model
    return verified
