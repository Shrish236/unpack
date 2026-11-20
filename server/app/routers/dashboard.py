"""Read endpoints for the executive and manager dashboard pages. Dummy data until the pipeline measures it.

Every route needs a logged-in viewer. The dashboards are company-wide, so there is no per-repo check.
Field names are snake_case, like the rest of the API.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..dashboard_seed import TYPES
from ..db import get_db
from ..deps import viewer
from ..errors import ApiError
from ..config import settings
from ..pipeline.metrics import exec_metrics, monday, team_metrics
from ..pipeline.rollup import load_sessions, measured_summary
from ..models import (
    ConsistencyItem,
    ConsistencyRow,
    ExecAgent,
    ExecHumanKind,
    ExecPeriod,
    ExecPolicyEvent,
    ExecWeek,
    GovCandidate,
    GovPolicy,
    Team,
    TeamArea,
    TeamAreaWeek,
    TeamMix,
    TeamPR,
    TeamSuggestion,
    TeamTool,
)

router = APIRouter(prefix="/api/dashboard", dependencies=[Depends(viewer)])

WINDOW_WEEKS = {"30d": 5, "90d": 12}
PENDING_WINDOW_DAYS = 90  # policies expiring within this many days are listed as expiring


def _today() -> date:
    return datetime.now(timezone.utc).date()


@router.get("/exec")
async def executive_page(period: Literal["30d", "90d"] = "30d", db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    stats = await db.get(ExecPeriod, period)
    if stats is None:
        # Clean (unseeded) DB: start with zeroed defaults so measured sessions can still populate the page.
        stats = ExecPeriod(
            period=period, adherence=0, adherence_delta=0, override=0.0, override_before=0.0,
            verified=0, verified_delta=0, unrequested=0, unrequested_delta=0,
            pending=0, pending_oldest_days=0, sessions=0, rework_first=0, rework_missed=0, rework_thin=0,
        )

    weeks = list((await db.execute(select(ExecWeek).order_by(ExecWeek.week_start))).scalars())
    window = weeks[-WINDOW_WEEKS[period]:]
    in_window = {w.week_start: i for i, w in enumerate(window)}
    position = {w.week_start: i for i, w in enumerate(weeks)}

    events = list((await db.execute(select(ExecPolicyEvent).order_by(ExecPolicyEvent.week_start))).scalars())
    headline = None
    for e in events:
        if e.headline and position.get(e.week_start, 0) > 0:
            headline = {
                "id": e.id,
                "before": weeks[position[e.week_start] - 1].repeat_overrides,
                "after": weeks[-1].repeat_overrides,
            }

    human_kinds = (await db.execute(select(ExecHumanKind).order_by(ExecHumanKind.position))).scalars()
    agents = (await db.execute(select(ExecAgent).order_by(ExecAgent.position))).scalars()
    open_candidates = (await db.execute(
        select(GovCandidate).where(GovCandidate.status == "open")
        .order_by(GovCandidate.developers.desc(), GovCandidate.sessions.desc()).limit(3)
    )).scalars()
    today = _today()
    active = (await db.execute(
        select(GovPolicy).where(GovPolicy.status == "active", GovPolicy.expires <= today + timedelta(days=PENDING_WINDOW_DAYS))
        .order_by(GovPolicy.expires)
    )).scalars()

    result = {
        "period": period,
        "weeks": [w.week_start.isoformat() for w in window],
        "adherence": [w.adherence for w in window],
        "repeat_overrides": [w.repeat_overrides for w in window],
        "human_per_week": [w.human_decisions for w in window],
        "mix": {t: [w.mix[t] for w in window] for t in TYPES},
        "policy_events": [
            {"id": e.id, "week": in_window[e.week_start], "text": e.text}
            for e in events if e.week_start in in_window
        ],
        "headline": headline,
        "kpis": {
            "adherence": {"v": stats.adherence, "d": stats.adherence_delta},
            "override": {"v": stats.override, "before": stats.override_before},
            "verified": {"v": stats.verified, "d": stats.verified_delta},
            "unrequested": {"v": stats.unrequested, "d": stats.unrequested_delta},
            "pending": {"v": stats.pending, "oldest_days": stats.pending_oldest_days},
            "sessions": stats.sessions,
        },
        "rework": {"first": stats.rework_first, "missed": stats.rework_missed, "thin": stats.rework_thin},
        "human_kinds": [{"kind": h.kind, "label": h.label, "pct": h.pct} for h in human_kinds],
        "agents": [
            {"name": a.name, "tool": a.tool, "decisions": a.decisions, "verified": a.verified,
             "unrequested": a.unrequested, "attempts": a.attempts, "autonomy": a.autonomy}
            for a in agents
        ],
        "measured": await measured_summary(db),
        "backlog": [
            {"id": c.pid, "statement": c.statement, "sessions": c.sessions, "teams": c.teams,
             "developers": c.developers, "waiting_days": (today - c.first_seen).days}
            for c in open_candidates
        ],
        "expiring": [
            {"id": p.id, "statement": p.statement, "in_days": (p.expires - today).days, "owner": p.owner}
            for p in active
        ],
    }
    result["sources"] = {k: "sample" for k in EXEC_SECTIONS}
    data = await load_sessions(db)
    measured = exec_metrics(data, today, WINDOW_WEEKS[period]) if len(data) >= settings.METRICS_MIN_SESSIONS else None
    if measured:
        _overlay_exec(result, measured, events, today)
        _overlay_pending(result, await _open_candidates(db), today)
    return result


EXEC_SECTIONS = ("trend", "kpis", "rework", "human_kinds", "agents")


async def _open_candidates(db: AsyncSession) -> list[GovCandidate]:
    return list((await db.execute(select(GovCandidate).where(GovCandidate.status == "open"))).scalars())


def _overlay_pending(result: dict[str, Any], open_candidates: list[GovCandidate], today: date) -> None:
    waiting = [(today - c.first_seen).days for c in open_candidates]
    result["kpis"]["pending"] = {"v": len(open_candidates), "oldest_days": max(waiting, default=0)}


def _overlay_exec(result: dict[str, Any], m: dict[str, Any], events: list[ExecPolicyEvent], today: date) -> None:
    """Replace the sample sections with the ones measured from sessions. A section the sessions cannot fill stays sample."""
    for key in ("weeks", "adherence", "repeat_overrides", "human_per_week", "mix"):
        result[key] = m[key]
    result["sources"]["trend"] = "measured"
    week_of = {date.fromisoformat(w): i for i, w in enumerate(m["weeks"])}
    result["policy_events"] = [{"id": e.id, "week": week_of[monday(e.week_start)], "text": e.text}
                               for e in events if monday(e.week_start) in week_of]
    result["headline"] = None
    for e in events:
        i = week_of.get(monday(e.week_start))
        if e.headline and i:
            before, after = m["repeat_overrides"][i - 1], next((v for v in reversed(m["repeat_overrides"]) if v is not None), None)
            if before is not None and after is not None:
                result["headline"] = {"id": e.id, "before": before, "after": after}
    pending = result["kpis"]["pending"]
    result["kpis"] = {**m["kpis"], "pending": pending}
    result["sources"]["kpis"] = "measured"
    result["rework"] = m["rework"]
    result["sources"]["rework"] = "measured"
    if m["human_kinds"] is not None:
        result["human_kinds"] = m["human_kinds"]
        result["sources"]["human_kinds"] = "measured"
    if m["agents"]:
        result["agents"] = m["agents"]
        result["sources"]["agents"] = "measured"


@router.get("/teams")
async def teams_index(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    teams = list((await db.execute(select(Team).order_by(Team.position))).scalars())
    items = list((await db.execute(select(ConsistencyItem).order_by(ConsistencyItem.position))).scalars())
    rows = (await db.execute(
        select(ConsistencyRow).join(Team, Team.id == ConsistencyRow.team_id).order_by(Team.position)
    )).scalars().all()
    by_item: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_item[r.item_id].append({"team": r.team_id, "approach": r.approach, "prs": r.prs})
    return {
        "teams": [{"id": t.id, "name": t.name} for t in teams],
        "consistency": [
            {"id": i.id, "type": i.type, "question": i.question, "rows": by_item[i.id]} for i in items
        ],
    }


@router.get("/teams/{team_id}")
async def team_page(team_id: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    team = await db.get(Team, team_id)
    if team is None:
        raise ApiError(404, "not_found", "no such team")

    areas = list((await db.execute(
        select(TeamArea).where(TeamArea.team_id == team_id).order_by(TeamArea.position)
    )).scalars())
    area_weeks = (await db.execute(
        select(TeamAreaWeek).join(TeamArea, TeamArea.id == TeamAreaWeek.area_id).where(TeamArea.team_id == team_id)
    )).scalars().all()
    weeks = sorted({w.week_start for w in area_weeks})
    week_index = {w: i for i, w in enumerate(weeks)}
    cells: dict[int, dict[date, TeamAreaWeek]] = defaultdict(dict)
    for w in area_weeks:
        cells[w.area_id][w.week_start] = w

    suggestions = (await db.execute(
        select(TeamSuggestion).where(TeamSuggestion.team_id == team_id).order_by(TeamSuggestion.position)
    )).scalars()
    mix = sorted((await db.execute(select(TeamMix).where(TeamMix.team_id == team_id))).scalars(),
                 key=lambda m: TYPES.index(m.type))
    tools = (await db.execute(
        select(TeamTool).where(TeamTool.team_id == team_id).order_by(TeamTool.calls.desc())
    )).scalars()
    pr_rows = list((await db.execute(
        select(TeamPR).where(TeamPR.team_id == team_id).order_by(TeamPR.week_start.desc(), TeamPR.number.desc())
    )).scalars())
    prs = pr_rows

    result = {
        "id": team.id,
        "name": team.name,
        "weeks": [w.isoformat() for w in weeks],
        "kpis": {
            "prs": team.prs, "prs_delta": team.prs_delta, "attempts": team.attempts,
            "attempts_delta": team.attempts_delta, "overrules": team.overrules,
            "thin": team.thin, "unsupported": team.unsupported,
        },
        "areas": [
            {
                "path": a.path,
                "attempts": [cells[a.id][w].attempts if w in cells[a.id] else 0.0 for w in weeks],
                "overrules": [cells[a.id][w].overrules if w in cells[a.id] else 0 for w in weeks],
            }
            for a in areas
        ],
        "funnel": {
            "total": team.funnel_total,
            "first": team.funnel_first,
            "second": {"agent": team.funnel_second_agent, "thin": team.funnel_second_thin},
            "third": {"agent": team.funnel_third_agent, "thin": team.funnel_third_thin},
        },
        "suggestions": [{"cause": s.cause, "text": s.text, "prs": list(s.prs)} for s in suggestions],
        "mix": [{"type": m.type, "agent": m.agent, "human": m.human} for m in mix],
        "tools": [{"name": t.name, "calls": t.calls, "tokens": t.tokens} for t in tools],
        "prs": [
            {
                "number": p.number, "title": p.title, "area": p.area, "week": week_index.get(p.week_start, -1),
                "agent": p.agent, "agent_decisions": p.agent_decisions, "human_decisions": p.human_decisions,
                "overrules": p.overrules, "attempts": p.attempts, "flags": list(p.flags), "source": p.source,
                "public_id": p.public_id,
            }
            for p in prs
        ],
    }
    result["sources"] = {k: "sample" for k in TEAM_SECTIONS}
    if team_id == settings.DASHBOARD_TEAM_ID:  # measured sessions are all attributed to this team until teams are mapped
        data = await load_sessions(db)
        m = team_metrics(data, _today()) if len(data) >= settings.METRICS_MIN_SESSIONS else None
        if m:
            for key in ("weeks", "kpis", "areas", "funnel", "mix", "tools"):
                result[key] = m[key]
            for section in ("kpis", "areas", "funnel", "mix", "tools"):
                result["sources"][section] = "measured"
            index = {date.fromisoformat(w): i for i, w in enumerate(m["weeks"])}
            for out, row in zip(result["prs"], pr_rows):
                out["week"] = index.get(row.week_start, -1)
    return result


TEAM_SECTIONS = ("kpis", "areas", "funnel", "suggestions", "mix", "tools", "consistency")
