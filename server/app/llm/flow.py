"""The model's reading flow: stages and an order for the changed functions.

The model sees the verified reasons and the call edges between changed functions, not the session, so this call is
small. Its answer is checked: unknown labels are dropped, a function listed twice keeps its first place, and every
changed function that the model left out is appended in the deterministic order. The result always lists every
changed function exactly once.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..config import settings
from .budget import LLMBudget
from .client import LLMCallRecord, LLMFlowOutput, run_structured_llm
from .prompt_text import flow_prompt, labels_line, response_section

FLOW_PROMPT_VERSION = 2
NOTE_MAX = 240


@dataclass
class FlowResult:
    variant: dict[str, Any] | None = None  # {mode, stages, order} or None
    model: str | None = None
    warnings: list[str] = field(default_factory=list)
    calls: list[LLMCallRecord] = field(default_factory=list)
    error: str | None = None
    quota: bool = False


def build_flow_prompt(
    graph: dict[str, Any], det_order: list[str], reasons: dict[str, dict[str, Any]], task: str,
) -> tuple[str, str, dict[str, str]]:
    """Returns (system, user, label -> node id). Only live changed functions are sent, up to MAX_LLM_FUNCTIONS."""
    nodes = {n["id"]: n for n in graph["nodes"]}
    sent = [i for i in det_order if i in nodes and nodes[i]["layer"] == "changed"][: settings.MAX_LLM_FUNCTIONS]
    label_of = {nid: f"F{i}" for i, nid in enumerate(sent, start=1)}
    sent_set = set(sent)
    callees: dict[str, list[str]] = {i: [] for i in sent}
    callers: dict[str, list[str]] = {i: [] for i in sent}
    for e in graph["edges"]:
        if e["kind"] == "CALLS" and e["source"] in sent_set and e["target"] in sent_set and e["source"] != e["target"]:
            callees[e["source"]].append(label_of[e["target"]])
            callers[e["target"]].append(label_of[e["source"]])

    lines = ["## TASK", (task or "(no task text recorded)")[:1500], "", "## CHANGED FUNCTIONS"]
    for nid in sent:
        n = nodes[nid]
        reason = (reasons.get(nid) or {}).get("reason", "")
        change = (n.get("change") or {}).get("kind", "changed")
        test = (n.get("test") or {}).get("label", "none")
        lines.append(f"{label_of[nid]} {n['path']}::{n['label']} ({change}, tests: {test})")
        if reason:
            lines.append(f"   why: {reason[:300]}")
        lines.append(f"   calls: {', '.join(callees[nid]) or 'none of the others'}; called by: {', '.join(callers[nid]) or 'none of the others'}")
    lines += ["", "## DEFAULT ORDER (callers before callees; change it if the story reads better another way)",
              " ".join(label_of[i] for i in sent)]
    system = flow_prompt(FLOW_PROMPT_VERSION)
    lines.append("")
    lines.append(response_section([
        'Reply with one JSON object with the keys "stages" and "uncovered", as described in the system prompt.',
        f"Labels you may use, each at most once: {labels_line(list(label_of.values()))}.",
    ]))
    return system, "\n".join(lines), {v: k for k, v in label_of.items()}


def verify_flow(
    output: LLMFlowOutput, label_to_node: dict[str, str], graph: dict[str, Any], det_order: list[str],
) -> tuple[dict[str, Any] | None, list[str]]:
    """Turn the model's answer into a flow variant that lists every changed node once. None if nothing usable came back."""
    warnings: list[str] = []
    used: set[str] = set()
    stages: list[dict[str, Any]] = []
    dropped = 0
    for idx, st in enumerate(output.stages, start=1):
        steps: list[dict[str, Any]] = []
        for step in st.steps:
            nid = label_to_node.get(step.fn.strip())
            if nid is None or nid in used:
                dropped += 1
                continue
            used.add(nid)
            steps.append({"node": nid, "role": step.role, "note": step.note.strip()[:NOTE_MAX]})
        if not steps:
            continue
        stages.append({
            "title": (st.title.strip() or f"Stage {idx}")[:80], "summary": st.summary.strip()[:NOTE_MAX],
            "node_ids": [s["node"] for s in steps], "steps": steps,
        })
    if dropped:
        warnings.append(f"{dropped} step(s) named an unknown or repeated function and were dropped")
    if not stages:
        return None, warnings + ["the model returned no usable stages"]

    nodes = {n["id"]: n for n in graph["nodes"]}
    live_all = [i for i in det_order if i in nodes and nodes[i]["layer"] == "changed"]
    left = [i for i in live_all if i not in used]
    if left:
        warnings.append(f"{len(left)} function(s) were not placed by the model and are listed last")
        stages.append({"title": "Other changes", "summary": "Not placed in a stage by the model",
                       "node_ids": left, "steps": [{"node": i, "role": None, "note": ""} for i in left]})
    ghosts = [i for i in det_order if i in nodes and nodes[i]["layer"] == "ghost"]
    if ghosts:
        stages.append({"title": "Removed", "summary": "Functions deleted by this change", "node_ids": ghosts, "steps": []})
    order = [i for s in stages for i in s["node_ids"]]

    pos = {nid: k for k, nid in enumerate(order)}
    against = sum(1 for e in graph["edges"] if e["kind"] == "CALLS" and e["source"] in pos and e["target"] in pos
                  and pos[e["target"]] < pos[e["source"]])
    if against:
        warnings.append(f"{against} call(s) run against this order (a callee is read before its caller)")
    return {"mode": "llm", "stages": stages, "order": order}, warnings


async def run_flow(
    graph: dict[str, Any], det_order: list[str], reasons: dict[str, dict[str, Any]], task: str, budget: LLMBudget,
) -> FlowResult:
    live = [i for i in det_order if any(n["id"] == i and n["layer"] == "changed" for n in graph["nodes"])]
    if len(live) < 2:
        return FlowResult(error="fewer than two changed functions: nothing to order")
    if budget.exhausted():
        return FlowResult(error=budget.reason(), quota=budget.quota_hit)
    system, user, label_to_node = build_flow_prompt(graph, det_order, reasons, task)
    res = await run_structured_llm(
        system_prompt=system, user_prompt=user, schema=LLMFlowOutput, purpose="flow",
        prompt_version=FLOW_PROMPT_VERSION, daily_tokens_used=budget.used,
    )
    budget.record(res)
    if res.output is None:
        return FlowResult(calls=res.calls, error=res.error, quota=res.quota)
    variant, warnings = verify_flow(res.output, label_to_node, graph, det_order)
    return FlowResult(variant=variant, model=res.model, warnings=warnings, calls=res.calls,
                      error=None if variant else "no usable stages")
