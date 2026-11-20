"""Deterministic verification of LLM quotes, history turn IDs, and FACTS (§4.8)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..llm.client import LLMReasoningOutput
from ..pipeline.edit_linker import LinkOutcome
from ..pipeline.session import UnpackSession

NO_REASON_TEXT = "No reason found in the session"
TEXT_ONLY_REASON = "Comments or formatting only"

_QUOTE_TRANSLATION = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u00a0": " ",
    }
)
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass
class VerifiedReasoning:
    summary: str
    reasons: dict[str, dict[str, Any]]  # node_id -> reason dict (with optional 'rejected' key)
    findings: list[dict[str, Any]]
    rejected_count: int = 0
    claim_turns: list[tuple[str, str, int]] = field(default_factory=list)  # (turn_id, label, finding_idx)


def normalize_for_quote_match(text: str) -> str:
    """Normalize quote characters and collapse whitespace for verbatim substring checks."""
    translated = text.translate(_QUOTE_TRANSLATION)
    return _WHITESPACE_RE.sub(" ", translated).strip()


def quote_matches_turn(session: UnpackSession, turn_id: str, quote: str) -> bool:
    """Return True iff turn_id exists and quote appears verbatim in that turn's text."""
    turn = session.turns_by_id.get(turn_id)
    if turn is None:
        return False
    norm_quote = normalize_for_quote_match(quote)
    if not norm_quote:
        return False
    for haystack in turn.searchable_texts():
        if norm_quote in normalize_for_quote_match(haystack):
            return True
    return False


def _verify_evidence(
    session: UnpackSession, raw_evidence: list[Any]
) -> list[dict[str, str]]:
    verified: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in raw_evidence:
        turn_id = str(getattr(item, "turn", "") or "").strip()
        quote = str(getattr(item, "quote", "") or "").strip()
        if not turn_id or not quote:
            continue
        if quote_matches_turn(session, turn_id, quote):
            key = (turn_id, quote)
            if key not in seen:
                seen.add(key)
                verified.append({"turn": turn_id, "quote": quote})
    return verified


def _verify_history(
    session: UnpackSession, raw_history: list[Any]
) -> list[dict[str, str]]:
    """Keep only history steps whose turn ID exists in the parsed session."""
    valid: list[dict[str, str]] = []
    for step in raw_history:
        turn_id = str(getattr(step, "turn", "") or "").strip()
        text = str(getattr(step, "text", "") or "").strip()
        if not turn_id or not text:
            continue
        if turn_id in session.turns_by_id:
            valid.append({"turn": turn_id, "text": text})
    return valid


def _finding_contradicts_facts(
    kind: str,
    finding_text: str,
    resolved_nodes: list[str],
    link_outcome: LinkOutcome,
    nodes_by_id: dict[str, dict[str, Any]],
) -> bool:
    if kind == "not_tested_after_change":
        return link_outcome.tested_after_final_edit

    if kind == "claim_not_backed":
        lowered = finding_text.lower()
        # If the finding specifically claims referenced functions have no tests, verify against graph
        if resolved_nodes and any(
            phrase in lowered for phrase in ("no test", "not reached", "untested", "missing test")
        ):
            all_tested = True
            for nid in resolved_nodes:
                test_info = (nodes_by_id.get(nid) or {}).get("test") or {}
                if test_info.get("label", "none") == "none":
                    all_tested = False
                    break
            if all_tested:
                return True
    return False


def verify_reasoning_output(
    llm_output: LLMReasoningOutput,
    *,
    session: UnpackSession,
    link_outcome: LinkOutcome,
    alias_to_node: dict[str, str],
    target_node_ids: list[str],
    text_only_node_ids: list[str],
    graph_nodes: list[dict[str, Any]],
) -> VerifiedReasoning:
    """Verify every quote, driver rule, history turn ID, and fact constraint (§4.8)."""
    nodes_by_id = {n["id"]: n for n in graph_nodes}
    reasons: dict[str, dict[str, Any]] = {}
    rejected_count = 0

    # 1. Auto-label text_only functions locally (never sent to LLM)
    for nid in text_only_node_ids:
        link = link_outcome.links.get(nid)
        source = link.source if link else "outside_session"
        driver = "agent_decided" if source in ("session", "session_then_formatted") else "not_stated"
        reasons[nid] = {
            "reason": TEXT_ONLY_REASON,
            "driver": driver,
            "history": [],
            "confidence": "high",
            "source": source,
            "evidence": [],
            "rejected": None,
        }

    # 2. Verify each LLM function reason
    for item in llm_output.functions:
        node_id = alias_to_node.get(item.fn)
        if node_id is None:
            rejected_count += 1
            continue

        link = link_outcome.links.get(node_id)
        source = link.source if link else "outside_session"
        valid_evidence = _verify_evidence(session, item.evidence)
        valid_history = _verify_history(session, item.history)

        if item.driver == "not_stated":
            reasons[node_id] = {
                "reason": NO_REASON_TEXT,
                "driver": "not_stated",
                "history": valid_history,
                "confidence": item.confidence,
                "source": source,
                "evidence": valid_evidence,
                "rejected": None,
            }
            continue

        has_user_quote = any(
            session.turns_by_id[ev["turn"]].kind == "user"
            for ev in valid_evidence
            if ev["turn"] in session.turns_by_id
        )
        driver_ok = bool(valid_evidence) and (item.driver != "user_asked" or has_user_quote)

        if not driver_ok:
            rejected_count += 1
            reasons[node_id] = {
                "reason": NO_REASON_TEXT,
                "driver": "not_stated",
                "history": [],
                "confidence": "low",
                "source": source,
                "evidence": [],
                "rejected": {
                    "reason": item.reason,
                    "driver": item.driver,
                    "history": [{"turn": h.turn, "text": h.text} for h in item.history],
                    "evidence": [{"turn": e.turn, "quote": e.quote} for e in item.evidence],
                    "reject_reason": (
                        "user_asked requires at least one verified user-turn quote"
                        if valid_evidence and item.driver == "user_asked"
                        else "no verified verbatim quote"
                    ),
                },
            }
        else:
            reasons[node_id] = {
                "reason": item.reason.strip() or NO_REASON_TEXT,
                "driver": item.driver,
                "history": valid_history,
                "confidence": item.confidence,
                "source": source,
                "evidence": valid_evidence,
                "rejected": None,
            }

    # 3. Ensure every target function has a reason entry (missing -> not_stated)
    for nid in target_node_ids:
        if nid not in reasons:
            link = link_outcome.links.get(nid)
            reasons[nid] = {
                "reason": NO_REASON_TEXT,
                "driver": "not_stated",
                "history": [],
                "confidence": "low",
                "source": link.source if link else "outside_session",
                "evidence": [],
                "rejected": None,
            }

    # 4. Verify session_review findings
    findings: list[dict[str, Any]] = []
    claim_turns: list[tuple[str, str, int]] = []
    for raw_f in llm_output.session_review:
        valid_evidence = _verify_evidence(session, raw_f.evidence)
        if not valid_evidence:
            rejected_count += 1
            continue

        resolved_nodes = [
            alias_to_node[alias] for alias in raw_f.functions if alias in alias_to_node
        ]
        if _finding_contradicts_facts(
            raw_f.kind, raw_f.finding, resolved_nodes, link_outcome, nodes_by_id
        ):
            rejected_count += 1
            continue

        finding_idx = len(findings)
        findings.append(
            {
                "kind": raw_f.kind,
                "finding": raw_f.finding.strip(),
                "functions": resolved_nodes,
                "evidence": valid_evidence,
            }
        )
        if raw_f.kind == "claim_not_backed":
            claim_turns.append((valid_evidence[0]["turn"], raw_f.finding.strip()[:120], finding_idx))

    return VerifiedReasoning(
        summary=llm_output.summary.strip(),
        reasons=reasons,
        findings=findings,
        rejected_count=rejected_count,
        claim_turns=claim_turns,
    )
