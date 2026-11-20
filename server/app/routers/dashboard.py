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
from ..pipeline.rollup import measured_summary
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
        raise ApiError(404, "not_found", "no such period")

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

    return {
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
    prs = (await db.execute(
        select(TeamPR).where(TeamPR.team_id == team_id).order_by(TeamPR.week_start.desc(), TeamPR.number.desc())
    )).scalars()

    return {
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
            }
            for p in prs
        ],
    }
