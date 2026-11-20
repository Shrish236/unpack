"""Dashboard numbers measured from sessions: the executive page and one team's page.

Pure functions over the rows `rollup._load()` returns, so they are easy to test with made-up sessions. Each result
is None when no session falls in the window. The routers then keep the sample (seeded) numbers and say so. Where
a number cannot be worked out from what a session records, the function leaves that key out and the router keeps
the sample value for that section only.

Definitions (they are shown to the reader in the UI, so they must stay true):
- adherence:      decisions that followed a steering rule, as a share of decisions checked against a rule
- repeat override: human corrections whose statement recurs in at least CANDIDATE_MIN_SESSIONS sessions, per 100 sessions
- verified:       sessions whose last test run came after the final edit, with no claim the session does not back
- unrequested:    changed functions the agent chose on its own (driver agent_decided), as a share of explained functions
- rework:         a session needed rework when a person overrode the agent or the agent needed more than one attempt.
                  The cause is "thin" when a person added a requirement, otherwise the agent "missed" it.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any

from ..config import settings
from .rollup import AGENT_LABEL, OVERRIDE_KINDS, cluster

TYPES = ["architecture", "design", "dependency", "retries", "test", "scope"]
HUMAN_KIND_LABELS = [
    ("redirect", "Redirected the agent"), ("reject", "Rejected a proposal"), ("requirement", "Added a requirement"),
    ("discussion", "Chose in discussion"), ("permission_denied", "Denied a tool call"),
]


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def week_window(today: date, n: int) -> list[date]:
    this = monday(today)
    return [this - timedelta(weeks=n - 1 - i) for i in range(n)]


def _pct(num: int, den: int) -> int | None:
    return round(100 * num / den) if den else None


def _delta(now: int | None, before: int | None) -> int | None:
    return None if now is None or before is None else now - before


def _in(data: list[dict[str, Any]], start: date, end: date) -> list[dict[str, Any]]:
    """Sessions whose week starts in [start, end)."""
    return [d for d in data if start <= monday(d["when"]) < end]


def _adherence(sessions: list[dict[str, Any]]) -> int | None:
    checked = [x for d in sessions for x in d["decisions"] if x.rule_followed is not None]
    return _pct(sum(1 for x in checked if x.rule_followed), len(checked))


def is_verified(d: dict[str, Any]) -> bool:
    facts = d["facts"]
    flags = {f.get("flag") for f in d["signals"].get("flags", [])}
    return bool(facts.get("last_test_run")) and bool(facts.get("tested_after_final_edit")) and "unsupported" not in flags


def _unrequested(sessions: list[dict[str, Any]]) -> int | None:
    total = sum(sum(d["drivers"].values()) for d in sessions)
    return _pct(sum(d["drivers"].get("agent_decided", 0) for d in sessions), total)


def rework_cause(d: dict[str, Any]) -> str | None:
    """None when the session needed no rework, else 'thin' or 'missed'."""
    human = [x for x in d["decisions"] if x.actor == "human"]
    overrides = [x for x in human if x.kind in OVERRIDE_KINDS]
    requirements = [x for x in human if x.kind == "requirement"]
    needed = float(d["signals"].get("attempts", 1)) > 1 or bool(overrides) or bool(requirements)
    if not needed:
        return None
    return "thin" if requirements else "missed"


def rework_rounds(d: dict[str, Any]) -> int:
    human = [x for x in d["decisions"] if x.actor == "human" and x.kind in OVERRIDE_KINDS | {"requirement"}]
    return max(int(float(d["signals"].get("attempts", 1))) - 1, len(human))


def repeated_ids(data: list[dict[str, Any]]) -> set[int]:
    """Ids of human override decisions whose statement recurs across enough sessions."""
    items = [{"d": d, "x": x, "statement": x.statement, "type": x.type}
             for d in data for x in d["decisions"]
             if x.actor == "human" and x.statement and x.kind in OVERRIDE_KINDS]
    out: set[int] = set()
    for members in cluster(items):
        if len({m["d"]["analysis"].id for m in members}) >= settings.CANDIDATE_MIN_SESSIONS:
            out.update(m["x"].id for m in members)
    return out


def earned_autonomy(verified: int | None, unrequested: int | None) -> str | None:
    """Earned autonomy level from measured verification and unrequested-change rates."""
    if verified is None:
        return None
    if verified >= 80 and (unrequested is None or unrequested <= 10):
        return "advice"
    if verified >= 65 and (unrequested is None or unrequested <= 20):
        return "check"
    return "gate"


def exec_metrics(data: list[dict[str, Any]], today: date, n_weeks: int) -> dict[str, Any] | None:
    weeks = week_window(today, n_weeks)
    start, end = weeks[0], weeks[-1] + timedelta(weeks=1)
    prev_start = start - timedelta(weeks=n_weeks)
    cur, prev = _in(data, start, end), _in(data, prev_start, start)
    if not cur:
        return None
    repeated = repeated_ids(data)

    by_week: dict[date, list[dict[str, Any]]] = {w: [] for w in weeks}
    for d in cur:
        by_week[monday(d["when"])].append(d)

    def repeat_per_100(sessions: list[dict[str, Any]]) -> float | None:
        if not sessions:
            return None
        n = sum(1 for d in sessions for x in d["decisions"] if x.id in repeated)
        return round(100 * n / len(sessions), 1)

    human_all = [x for d in cur for x in d["decisions"] if x.actor == "human"]
    kinds = Counter(x.kind for x in human_all)
    rework = Counter(rework_cause(d) or "first" for d in cur)

    agents: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for d in cur:
        tool = AGENT_LABEL.get(d["signals"].get("agent", ""), d["signals"].get("agent") or "Agent")
        agents[(d["model"] or tool, tool)].append(d)

    out: dict[str, Any] = {
        "weeks": [w.isoformat() for w in weeks],
        "adherence": [_adherence(by_week[w]) for w in weeks],
        "repeat_overrides": [repeat_per_100(by_week[w]) for w in weeks],
        "human_per_week": [sum(1 for d in by_week[w] for x in d["decisions"] if x.actor == "human") for w in weeks],
        "mix": {t: [sum(1 for d in by_week[w] for x in d["decisions"] if x.type == t) for w in weeks] for t in TYPES},
        "kpis": {
            "adherence": {"v": _adherence(cur), "d": _delta(_adherence(cur), _adherence(prev))},
            "override": {"v": repeat_per_100(cur), "before": repeat_per_100(prev)},
            "verified": {"v": _pct(sum(is_verified(d) for d in cur), len(cur)),
                         "d": _delta(_pct(sum(is_verified(d) for d in cur), len(cur)),
                                     _pct(sum(is_verified(d) for d in prev), len(prev)))},
            "unrequested": {"v": _unrequested(cur), "d": _delta(_unrequested(cur), _unrequested(prev))},
            "sessions": len(cur),
        },
        "rework": {"first": rework["first"], "missed": rework["missed"], "thin": rework["thin"]},
        "human_kinds": [{"kind": k, "label": label, "pct": _pct(kinds[k], len(human_all)) or 0}
                        for k, label in HUMAN_KIND_LABELS] if human_all else [],
        "agents": [
            {
                "name": name, "tool": tool, "decisions": sum(1 for d in ds for x in d["decisions"] if x.actor == "agent"),
                "verified": (ver := _pct(sum(is_verified(d) for d in ds), len(ds))),
                "unrequested": (unreq := _unrequested(ds)),
                "attempts": round(sum(float(d["signals"].get("attempts", 1)) for d in ds) / len(ds), 2),
                "autonomy": earned_autonomy(ver, unreq),
            }
            for (name, tool), ds in sorted(agents.items(), key=lambda kv: -len(kv[1]))
        ],
    }
    return out


def team_metrics(data: list[dict[str, Any]], today: date, n_weeks: int = 8) -> dict[str, Any] | None:
    weeks = week_window(today, n_weeks)
    start, end = weeks[0], weeks[-1] + timedelta(weeks=1)
    cur, prev = _in(data, start, end), _in(data, start - timedelta(weeks=n_weeks), start)
    if not cur:
        return None

    def avg_attempts(ds: list[dict[str, Any]]) -> float:
        return round(sum(float(d["signals"].get("attempts", 1)) for d in ds) / len(ds), 2) if ds else 0.0

    areas: dict[str, dict[date, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for d in cur:
        areas[d["area"]][monday(d["when"])].append(d)

    def overrules(d: dict[str, Any]) -> int:
        return sum(1 for x in d["decisions"] if x.actor == "human" and x.kind in OVERRIDE_KINDS)

    causes = [(d, rework_cause(d), rework_rounds(d)) for d in cur]
    second = [(c, r) for _, c, r in causes if c and r == 1]
    third = [(c, r) for _, c, r in causes if c and r >= 2]
    agent_by_type, human_by_type = Counter(), Counter()
    tools: dict[str, dict[str, int]] = defaultdict(lambda: {"calls": 0, "tokens": 0})
    for d in cur:
        for x in d["decisions"]:
            (agent_by_type if x.actor == "agent" else human_by_type)[x.type] += 1
        for name, row in d["signals"].get("tool_stats", {}).items():
            tools[name]["calls"] += row.get("calls", 0)
            tools[name]["tokens"] += row.get("tokens", 0)
    n_prev = len(prev)
    return {
        "weeks": [w.isoformat() for w in weeks],
        "kpis": {
            "prs": len(cur), "prs_delta": f"{len(cur) - n_prev:+d}", "attempts": avg_attempts(cur),
            "attempts_delta": f"{avg_attempts(cur) - avg_attempts(prev):+.2f}" if prev else "n/a",
            "overrules": round(sum(overrules(d) for d in cur) / len(cur), 1),
            # shares of the PRs, like the sample numbers they replace
            "thin": round(100 * sum(1 for _, c, _ in causes if c == "thin") / len(cur)),
            "unsupported": round(100 * sum(1 for d in cur if any(f.get("flag") == "unsupported" for f in d["signals"].get("flags", []))) / len(cur)),
        },
        "areas": [
            {"path": path,
             "attempts": [avg_attempts(by[w]) for w in weeks],
             "overrules": [sum(overrules(d) for d in by[w]) for w in weeks]}
            for path, by in sorted(areas.items(), key=lambda kv: -sum(len(v) for v in kv[1].values()))[:8]
        ],
        "funnel": {
            "total": len(cur), "first": sum(1 for _, c, _ in causes if c is None),
            "second": {"agent": sum(1 for c, _ in second if c == "missed"), "thin": sum(1 for c, _ in second if c == "thin")},
            "third": {"agent": sum(1 for c, _ in third if c == "missed"), "thin": sum(1 for c, _ in third if c == "thin")},
        },
        "mix": [{"type": t, "agent": agent_by_type[t], "human": human_by_type[t]} for t in TYPES],
        "tools": [{"name": n, **v} for n, v in sorted(tools.items(), key=lambda kv: -kv[1]["calls"])],
    }
