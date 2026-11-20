"""Tie decisions to graph nodes and say how each one turned out.

The model may name the changed functions a decision is about (`nodes`). When it does not, the session's own
timeline says it: the edits that follow a decision are what the decision changed. Every decision then gets an
`outcome`, decided by rules over facts that are already verified, never by asking the model again:

- rule_violated: the agent went against a steering rule
- overruled:     an agent choice that a person redirected, rejected or refused within a few turns
- reverted:      the functions it touched were edited and then put back by the end of the session
- unverified:    a finding says a claim was not backed, a failing test was ignored or a check was weakened on its functions
- ok:            none of the above, and every decision a person made (except a violated rule)

The first matching rule wins, in the order above.
"""

from __future__ import annotations

import re
from typing import Any

WINDOW = 6  # turns after a decision in which an edit counts as its effect
OVERRULE_WINDOW = 4  # turns after an agent choice in which a human correction counts as overruling it
HUMAN_CORRECTIONS = {"redirect", "reject", "permission_denied"}
UNVERIFIED_FINDINGS = {"claim_not_backed", "test_failed_ignored", "check_weakened"}


def _n(turn: str) -> int:
    m = re.search(r"\d+", turn or "")
    return int(m.group()) if m else 0


def _changed_ids_by_path(graph_nodes: list[dict[str, Any]]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for n in graph_nodes:
        if n.get("layer") in ("changed", "ghost") and n.get("kind") in ("function", "method"):
            out.setdefault(n["path"], []).append(n["id"])
    return out


def link_nodes(decision: dict[str, Any], edits: list[dict[str, Any]], by_path: dict[str, list[str]], known: set[str]) -> list[str]:
    """Nodes for one decision when the model gave none."""
    t = _n(decision["turn"])
    if decision["kind"] == "permission_denied":
        text = f"{decision.get('quote', '')} {decision.get('proposal', '')}"
        hit = [i for path, ids in by_path.items() if path in text for i in ids]
        return [i for i in hit if i in known]
    nxt = [e for e in edits if _n(e["turn"]) >= t and _n(e["turn"]) - t <= WINDOW]
    if not nxt:
        return []
    first = min(nxt, key=lambda e: _n(e["turn"]))
    return [i for i in first.get("nodes", []) if i in known]


def attach_nodes_and_outcomes(
    decisions: list[dict[str, Any]], highlights: list[dict[str, Any]], timeline: list[dict[str, Any]],
    findings: list[dict[str, Any]], graph_nodes: list[dict[str, Any]],
) -> None:
    """Mutates `decisions` and `highlights` in place: adds `nodes` (when missing) and `outcome`."""
    known = {n["id"] for n in graph_nodes}
    by_path = _changed_ids_by_path(graph_nodes)
    edits = [e for e in timeline if e.get("kind") in ("edit", "out_of_band") and e.get("nodes")]
    reverted: set[str] = set()
    for e in timeline:
        if e.get("kind") == "edit" and e.get("reverted"):
            reverted.update(e.get("nodes", []))
    unverified: set[str] = set()
    for f in findings:
        if f.get("kind") in UNVERIFIED_FINDINGS:
            unverified.update(f.get("functions", []))
    corrections = [d for d in decisions if d["actor"] == "human" and d["kind"] in HUMAN_CORRECTIONS]

    for d in decisions:
        if not d.get("nodes"):
            d["nodes"] = link_nodes(d, edits, by_path, known)
        nodes = set(d["nodes"])
        t = _n(d["turn"])
        if d.get("rule_followed") is False:
            d["outcome"] = "rule_violated"
        elif d["actor"] == "human":
            d["outcome"] = "ok"  # a person's correction is not a bet that can turn out badly
        elif d["actor"] == "agent" and any(t < _n(c["turn"]) <= t + OVERRULE_WINDOW for c in corrections):
            d["outcome"] = "overruled"
        elif nodes & reverted:
            d["outcome"] = "reverted"
        elif nodes & unverified:
            d["outcome"] = "unverified"
        else:
            d["outcome"] = "ok"
    for h in highlights:
        h.setdefault("nodes", [])
