"""Read endpoints for the executive and manager dashboard pages. Dummy data until the pipeline measures it.

Every route needs a logged-in viewer. The dashboards are company-wide, so there is no per-repo check.
Field names are snake_case, like the rest of the API.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..dashboard_seed import TYPES
from ..db import get_db
from ..deps import viewer
from ..errors import ApiError
from ..config import settings
from ..pipeline.metrics import exec_metrics, monday, team_metrics, week_window
from ..pipeline.rollup import AGENT_LABEL, OVERRIDE_KINDS, load_sessions, measured_summary
from ..models import (
    Analysis,
    ConsistencyItem,
    ConsistencyRow,
    ExecAgent,
    ExecHumanKind,
    ExecPeriod,
    ExecPolicyEvent,
    ExecWeek,
    GovCandidate,
    GovPolicy,
    Push,
    Repo,
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
    repo_names = sorted({f"{d['repo'].owner}/{d['repo'].name}" for d in data})
    if not repo_names:
        repo_rows = (await db.execute(select(Repo).order_by(Repo.name))).scalars().all()
        repo_names = [f"{r.owner}/{r.name}" for r in repo_rows]
    result["repos"] = repo_names
    result["repo_count"] = len(repo_names)
    all_policies = list((await db.execute(
        select(GovPolicy).where(GovPolicy.status == "active", GovPolicy.published_on.is_not(None))
    )).scalars())
    measured = exec_metrics(data, today, WINDOW_WEEKS[period]) if len(data) >= settings.METRICS_MIN_SESSIONS else None
    if measured:
        _overlay_exec(result, measured, events, all_policies, today)
        _overlay_pending(result, await _open_candidates(db), today)
    return result


EXEC_SECTIONS = ("trend", "kpis", "rework", "human_kinds", "agents")


async def _open_candidates(db: AsyncSession) -> list[GovCandidate]:
    return list((await db.execute(select(GovCandidate).where(GovCandidate.status == "open"))).scalars())


def _overlay_pending(result: dict[str, Any], open_candidates: list[GovCandidate], today: date) -> None:
    waiting = [(today - c.first_seen).days for c in open_candidates]
    result["kpis"]["pending"] = {"v": len(open_candidates), "oldest_days": max(waiting, default=0)}


def _overlay_exec(
    result: dict[str, Any],
    m: dict[str, Any],
    events: list[ExecPolicyEvent],
    policies: list[GovPolicy],
    today: date,
) -> None:
    """Replace the sample sections with the ones measured from sessions. A section the sessions cannot fill stays sample."""
    for key in ("weeks", "adherence", "repeat_overrides", "human_per_week", "mix"):
        result[key] = m[key]
    result["sources"]["trend"] = "measured"
    week_of = {date.fromisoformat(w): i for i, w in enumerate(m["weeks"])}
    ev_by_id: dict[str, dict[str, Any]] = {}
    for e in events:
        if monday(e.week_start) in week_of:
            ev_by_id[e.id] = {"id": e.id, "week": week_of[monday(e.week_start)], "text": e.text}
    for p in policies:
        if p.published_on and monday(p.published_on) in week_of and p.id not in ev_by_id:
            ev_by_id[p.id] = {"id": p.id, "week": week_of[monday(p.published_on)], "text": p.statement}
    result["policy_events"] = sorted(ev_by_id.values(), key=lambda x: x["week"])
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
    result["human_kinds"] = m["human_kinds"]
    result["sources"]["human_kinds"] = "measured"
    if m["agents"]:
        result["agents"] = m["agents"]
        result["sources"]["agents"] = "measured"


def _match_repo(repo: Repo, query: str) -> bool:
    q = query.strip().lower()
    full = f"{repo.owner}/{repo.name}".lower()
    return q == full or q == repo.name.lower()


@router.get("/repos")
async def list_repos(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """List repositories present in the database, ordered by number of finished analyses."""
    counts = dict((await db.execute(
        select(Push.repo_id, func.count(Analysis.id))
        .join(Analysis, Analysis.push_id == Push.id)
        .where(Analysis.status == "done")
        .group_by(Push.repo_id)
    )).all())
    repos = list((await db.execute(select(Repo).order_by(Repo.name))).scalars())
    items = [
        {
            "id": r.id,
            "owner": r.owner,
            "name": r.name,
            "full_name": f"{r.owner}/{r.name}",
            "analyses": int(counts.get(r.id, 0)),
        }
        for r in repos
    ]
    items.sort(key=lambda x: (-x["analyses"], x["name"].lower()))
    return {"repos": items}


@router.get("/repo")
async def repo_dashboard(repo: str = Query(..., min_length=1), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Dynamic DB-backed dashboard for a single repository (used by the Managers / Team page)."""
    repos = list((await db.execute(select(Repo))).scalars())
    target = next((r for r in repos if _match_repo(r, repo)), None)
    if target is None:
        raise ApiError(404, "not_found", f"no repository matching {repo!r}")

    all_data = await load_sessions(db)
    data = [d for d in all_data if d["repo"].id == target.id]
    today = _today()
    m = team_metrics(data, today)
    if m is None:
        weeks = [w.isoformat() for w in week_window(today, 8)]
        m = {
            "weeks": weeks,
            "kpis": {"prs": 0, "prs_delta": "+0", "attempts": 0.0, "attempts_delta": "n/a", "overrules": 0.0, "thin": 0, "unsupported": 0},
            "areas": [],
            "funnel": {"total": 0, "first": 0, "second": {"agent": 0, "thin": 0}, "third": {"agent": 0, "thin": 0}},
            "mix": [{"type": t, "agent": 0, "human": 0} for t in TYPES],
            "tools": [],
        }

    week_idx = {date.fromisoformat(w): i for i, w in enumerate(m["weeks"])}
    prs = []
    for d in sorted(data, key=lambda x: x["analysis"].id, reverse=True):
        a, push, sig, decs, pr = d["analysis"], d["push"], d["signals"], d["decisions"], d["pr"]
        human = [x for x in decs if x.actor == "human"]
        title = (pr.title if pr and pr.title else (a.summary or f"{push.branch} @ {push.head_sha[:7]}"))[:90]
        pr_url = (pr.html_url or f"https://github.com/{target.owner}/{target.name}/pull/{pr.number}") if pr else None
        commit_url = f"https://github.com/{target.owner}/{target.name}/commit/{push.head_sha}"
        prs.append({
            "number": pr.number if pr else None,
            "short_sha": push.head_sha[:7],
            "branch": push.branch,
            "title": title,
            "area": d["area"],
            "week": week_idx.get(monday(d["when"]), -1),
            "agent": AGENT_LABEL.get(sig.get("agent", ""), sig.get("agent") or "Agent"),
            "agent_decisions": sum(1 for x in decs if x.actor == "agent"),
            "human_decisions": len(human),
            "overrules": sum(1 for x in human if x.kind in OVERRIDE_KINDS),
            "attempts": float(sig.get("attempts", 1)),
            "flags": [f["flag"] for f in sig.get("flags", [])],
            "source": "measured",
            "public_id": a.public_id,
            "pr_url": pr_url,
            "commit_url": commit_url,
        })

    # Dynamic suggestions from human requirement additions and repeated overrides in this repo
    suggestions: list[dict[str, Any]] = []
    seen_stmt: set[str] = set()
    for d in sorted(data, key=lambda x: x["analysis"].id, reverse=True):
        for x in d["decisions"]:
            if x.actor != "human" or not x.statement:
                continue
            key = x.statement.strip().lower()
            if key in seen_stmt:
                continue
            seen_stmt.add(key)
            cause = "requirement-thin" if x.kind == "requirement" else "agent-missed"
            suggestions.append({
                "cause": cause,
                "text": x.statement,
                "prs": [d["pr"].number] if d["pr"] else [],
                "public_ids": [d["analysis"].public_id],
            })
            if len(suggestions) >= 5:
                break
        if len(suggestions) >= 5:
            break

    full_name = f"{target.owner}/{target.name}"
    return {
        "id": full_name,
        "name": target.name,
        "full_name": full_name,
        "sources": {k: "measured" for k in TEAM_SECTIONS},
        "weeks": m["weeks"],
        "kpis": m["kpis"],
        "areas": m["areas"],
        "funnel": m["funnel"],
        "suggestions": suggestions,
        "mix": m["mix"],
        "tools": m["tools"],
        "prs": prs,
        "consistency": [],
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
