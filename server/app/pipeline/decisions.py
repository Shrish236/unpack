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
from ..llm.client import LLMCallRecord, LLMDecisionOutput, run_structured_llm
from ..llm.prompt_builder import PROMPTS_DIR, _format_turn_for_llm
from .session import UnpackSession
from .steering import SteeringSnapshot
from .verify import quote_matches_turn

DECISIONS_PROMPT_VERSION = 2
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


def build_decision_prompt(
    session: UnpackSession, steering: SteeringSnapshot, signals: dict[str, Any], code_context: str | None = None,
) -> tuple[str, str]:
    system = (PROMPTS_DIR / f"decisions_v{DECISIONS_PROMPT_VERSION}.md").read_text(encoding="utf-8")
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
        sections.append("\n## CHANGED CODE\n" + code_context)
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
    return system, "\n".join(sections)


def verify_decisions(output: LLMDecisionOutput, session: UnpackSession, steering: SteeringSnapshot) -> DecisionResult:
    rule_ids = {r.id for r in steering.rules}
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
            "source": "llm", "verified": True,
        })
    for h in output.highlights[:4]:
        if h.turn in session.turns_by_id and (not h.quote or quote_matches_turn(session, h.turn, h.quote)):
            result.highlights.append({"kind": h.kind, "text": h.text[:300], "turn": h.turn, "quote": h.quote[:400]})
        else:
            result.rejected_count += 1
    return result


async def extract_decisions(
    session: UnpackSession, steering: SteeringSnapshot, signals: dict[str, Any], *, daily_tokens_used: int = 0,
    code_context: str | None = None,
) -> DecisionResult:
    """Parsed decisions always; LLM decisions when reasoning is enabled and the call succeeds."""
    parsed = denied_decisions(signals)
    if not settings.REASONING_ENABLED:
        return DecisionResult(decisions=parsed, error="reasoning disabled")
    system, user = build_decision_prompt(session, steering, signals, code_context)
    res = await run_structured_llm(
        system_prompt=system, user_prompt=user, schema=LLMDecisionOutput, purpose="decisions",
        prompt_version=DECISIONS_PROMPT_VERSION, daily_tokens_used=daily_tokens_used,
    )
    if res.output is None:
        return DecisionResult(decisions=parsed, llm_calls=res.calls, error=res.error)
    verified = verify_decisions(res.output, session, steering)
    verified.decisions = sorted(parsed + verified.decisions, key=lambda d: int(d["turn"][1:]))
    verified.llm_calls = res.calls
    verified.model = res.model
    return verified
