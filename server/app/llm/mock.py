"""A stand-in for Gemini that answers from the prompt itself, so the whole pipeline can run with no API key and no quota.

Turn it on with `GEMINI_BACKEND=mock` (and `REASONING_ENABLED=true`). It receives exactly the system and user prompts the
real model would, reads the sections the prompts promise (`## TASK`, `## CHANGED FUNCTIONS`, `## SESSION` ...) and writes JSON
that matches the response schema. Quotes are copied from the turns it was shown, so they pass the same verification a real
answer must pass.

That makes it a test of the prompts as much as of the code: if a section the model needs is missing or renamed, the mock
cannot find it and its answer degrades the way a model's would. It is deterministic. It is not smart, and the model name it
reports is `mock-gemini` so a stored analysis can never be mistaken for a real one.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel

from .client import RawLLMResponse

MOCK_MODEL = "mock-gemini"
_TURN_LINE = re.compile(r"^\[(T\d+)\] (user|assistant|thought|shell|edit|read|error|plan)(?:: ?| )(.*)$")
_FN_LINE = re.compile(r"^(F\d+) (\S+)\s+\((\w+), source: (\w+)\)")
_NODE_ID = re.compile(r"(\S+::\S+)")
_REJECT_WORDS = re.compile(r"\b(no|don't|do not|dont|never|instead|not that|stop|revert)\b", re.I)
_TYPE_WORDS = [
    ("dependency", re.compile(r"depend|package|install|library|pip|npm", re.I)),
    ("test", re.compile(r"\btests?\b|pytest|coverage", re.I)),
    ("retries", re.compile(r"retr(y|ies)|backoff", re.I)),
    ("architecture", re.compile(r"architecture|module|layer|structure", re.I)),
    ("scope", re.compile(r"only|just|scope|also|too", re.I)),
]


def _section(prompt: str, title: str) -> str:
    """The text under `## title ...` up to the next `## ` heading, or ''."""
    m = re.search(rf"^## {re.escape(title)}[^\n]*\n(.*?)(?=^## |\Z)", prompt, re.S | re.M)
    return m.group(1) if m else ""


def _turns(prompt: str) -> list[tuple[str, str, str]]:
    """(turn id, kind, first line of text) for every turn in ## SESSION."""
    out = []
    for line in _section(prompt, "SESSION").splitlines():
        m = _TURN_LINE.match(line)
        if m:
            out.append((m.group(1), m.group(2), m.group(3).strip()))
    return out


def _task(prompt: str) -> list[tuple[str, str]]:
    return [(m.group(1), m.group(2).strip()) for line in _section(prompt, "TASK").splitlines()
            if (m := re.match(r"^\[(T\d+)\] (.*)$", line))]


def _quote(text: str, limit: int = 70) -> str:
    """A verbatim slice of a turn's text: whole words, no leading or trailing space."""
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return (cut or text[:limit]).strip()


def _type_of(text: str) -> str:
    return next((name for name, rx in _TYPE_WORDS if rx.search(text)), "design")


def _functions(prompt: str) -> list[dict[str, Any]]:
    fns: list[dict[str, Any]] = []
    for line in _section(prompt, "CHANGED FUNCTIONS").splitlines():
        m = _FN_LINE.match(line)
        if m:
            fns.append({"fn": m.group(1), "id": m.group(2), "change": m.group(3), "source": m.group(4), "edits": []})
        elif fns and line.strip().startswith("edits:"):
            fns[-1]["edits"] = re.findall(r"T\d+", line)
    return fns


def reasons_answer(prompt: str) -> dict[str, Any]:
    users = [(t, x) for t, k, x in _turns(prompt) if k == "user"] or _task(prompt)
    claims = [(t, x) for t, k, x in _turns(prompt) if k == "assistant"]
    facts = _section(prompt, "FACTS")
    task_turn, task_text = users[0] if users else ("T1", "")
    functions = []
    for f in _functions(prompt):
        if f["source"] == "outside_session" or not users:
            functions.append({"fn": f["fn"], "reason": "No reason found in the session", "driver": "not_stated",
                              "history": [], "evidence": [], "confidence": "low"})
            continue
        name = f["id"].split("::", 1)[-1]
        functions.append({
            "fn": f["fn"], "reason": f"Mock: {name} was changed ({f['change']}) as part of: {_quote(task_text, 90)}",
            "driver": "user_asked",
            "history": [{"turn": t, "text": f"Edited {name}"} for t in f["edits"][:3]],
            "evidence": [{"turn": task_turn, "quote": _quote(task_text)}],
            "confidence": "medium",
        })
    review = []
    no_test_after = re.search(r"No test run after final edit \S+\? -> true", facts)
    ids = [f["fn"] for f in _functions(prompt)][:1]
    if claims and re.search(r"\btests?\b", claims[-1][1], re.I) and "Last test run: none" in facts:
        review.append({"kind": "claim_not_backed", "finding": "Mock: the agent mentions tests but none ran in the session",
                       "functions": ids, "evidence": [{"turn": claims[-1][0], "quote": _quote(claims[-1][1])}]})
    elif no_test_after and claims:
        review.append({"kind": "not_tested_after_change", "finding": "Mock: nothing was tested after the final edit",
                       "functions": ids, "evidence": [{"turn": claims[-1][0], "quote": _quote(claims[-1][1])}]})
    return {"summary": f"Mock summary: {_quote(task_text, 100)}", "functions": functions, "session_review": review}


def decisions_answer(prompt: str) -> dict[str, Any]:
    turns = _turns(prompt)
    users = [(t, x) for t, k, x in turns if k == "user"] or _task(prompt)
    steering = re.findall(r"^(S\d+) \([^)]*\): (.*)$", _section(prompt, "STEERING"), re.M)
    node_ids = [m.group(1) for line in _section(prompt, "CHANGED CODE").splitlines() if (m := _NODE_ID.search(line))
                and not line.startswith(" ")]
    decisions: list[dict[str, Any]] = []
    for turn, text in users[1:]:  # the first user turn is the task; later ones are the person stepping in
        kind = "reject" if _REJECT_WORDS.search(text) else "requirement"
        typ = _type_of(text)
        rule = next(((sid, rt) for sid, rt in steering if typ in rt.lower()), (None, ""))
        decisions.append({
            "turn": turn, "actor": "human", "kind": kind, "type": typ, "proposal": "What the agent was doing",
            "choice": _quote(text, 120), "statement": re.sub(r"\s+", " ", text).strip().rstrip(".")[:120],
            "quote": _quote(text), "rule_id": rule[0], "rule_followed": (False if rule[0] else None),
            "nodes": node_ids[:1],
        })
    agent = next(((t, x) for t, k, x in turns if k == "assistant"), None)
    if agent:
        decisions.append({
            "turn": agent[0], "actor": "agent", "kind": "choice", "type": _type_of(agent[1]), "proposal": "Options for the change",
            "choice": _quote(agent[1], 120), "statement": "", "quote": _quote(agent[1]), "rule_id": None, "rule_followed": None,
            "nodes": node_ids[:2],
        })
    highlights = []
    # a passing test run: the turn id is the last `[T#]` heading above the line that says "N passed"
    current, passed = None, None
    for line in _section(prompt, "SESSION").splitlines():
        head = re.match(r"^\[(T\d+)\]", line)
        if head:
            current = head.group(1)
        m = re.search(r"\d+ passed", line)
        if m and current:
            passed = (current, m.group(0))
    if passed:
        highlights.append({"kind": "went_right", "text": "A test run passed", "turn": passed[0], "quote": passed[1],
                           "nodes": node_ids[:1]})
    return {"decisions": decisions, "highlights": highlights}


def flow_answer(prompt: str) -> dict[str, Any]:
    fns = [(m.group(1), m.group(2)) for line in _section(prompt, "CHANGED FUNCTIONS").splitlines() if (m := re.match(r"^(F\d+) (\S+)", line))]
    why = dict(re.findall(r"^(F\d+) .*\n   why: (.*)$", _section(prompt, "CHANGED FUNCTIONS"), re.M))
    if not fns:
        return {"stages": [], "uncovered": []}
    split = max(1, (len(fns) + 1) // 2)

    def step(i: int, label: str, nid: str) -> dict[str, str]:
        role = "test" if re.search(r"(^|/)tests?(/|_)|test_", nid) else ("entry" if i == 0 else "logic")
        return {"fn": label, "role": role, "note": (why.get(label) or "")[:120]}
    stages = [{"title": "Entry and core logic", "summary": "Mock: where the work starts",
               "steps": [step(i, *f) for i, f in enumerate(fns[:split])]}]
    if fns[split:]:
        stages.append({"title": "Supporting changes", "summary": "Mock: what the core logic relies on",
                       "steps": [step(i + 1, *f) for i, f in enumerate(fns[split:])]})
    return {"stages": stages, "uncovered": []}


_ANSWERS = {"LLMReasoningOutput": reasons_answer, "LLMDecisionOutput": decisions_answer, "LLMFlowOutput": flow_answer}


class MockLLMClient:
    """Implements the LLMClient protocol. Records every request so tests can inspect what the model would have received."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    async def generate_json(
        self, *, model: str, system_prompt: str, user_prompt: str, response_schema: type[BaseModel],
        temperature: float | None = None, max_output_tokens: int = 0, timeout_s: int = 0,
    ) -> RawLLMResponse:
        name = response_schema.__name__
        self.requests.append({"schema": name, "model": model, "system": system_prompt, "user": user_prompt})
        answer = _ANSWERS[name](user_prompt)
        text = json.dumps(answer)
        # token counts follow the prompt size, so the daily budget and the dashboards see plausible numbers
        return RawLLMResponse(text=text, model=MOCK_MODEL, input_tokens=(len(system_prompt) + len(user_prompt)) // 4,
                              output_tokens=len(text) // 4, finish_reason="STOP")
