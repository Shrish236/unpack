"""Roll measured decisions up into the dashboard tables.

Idempotent: every run deletes the rows marked `source = 'measured'` and rebuilds them from the decisions and
signals stored for finished analyses. Sample rows (the seeded baseline) are never touched. The executive page
reads `measured_summary()` for its live strip.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import session_scope
from ..models import (
    Analysis, Decision, FunctionReason, GovCandidate, GovEvidence, GovSkillRule, PRAnalysis, PullRequest, Push, Repo,
    SessionSignals, Team, TeamPR,
)

OVERRIDE_KINDS = {"redirect", "reject", "permission_denied"}
AGENT_LABEL = {"gemini-cli": "Gemini CLI", "antigravity-cli": "Antigravity CLI", "claude-code": "Claude Code"}
_STOP = {"a", "an", "the", "to", "of", "for", "in", "on", "and", "or", "do", "not", "no", "never", "without", "use", "new", "add", "is", "be", "it", "that", "this", "don", "dont", "should", "must", "always"}
JACCARD_MIN = 0.4


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _stem(word: str) -> str:
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def _tokens(statement: str) -> frozenset[str]:
    words = re.findall(r"[a-z0-9]+", statement.lower())
    return frozenset(_stem(w) for w in words if w not in _STOP and len(w) > 2)


def cluster(items: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Greedy grouping of human decisions of one type whose statements share enough words."""
    groups: list[tuple[frozenset[str], str, list[dict[str, Any]]]] = []
    for it in items:
        toks = _tokens(it["statement"])
        if not toks:
            continue
        for i, (gtoks, gtype, members) in enumerate(groups):
            union = len(toks | gtoks)
            if it["type"] == gtype and union and len(toks & gtoks) / union >= JACCARD_MIN:
                members.append(it)
                groups[i] = (gtoks | toks, gtype, members)
                break
        else:
            groups.append((toks, it["type"], [it]))
    return [m for _, _, m in groups]


def _area(graph_view: dict[str, Any], default: str) -> str:
    counts: Counter[str] = Counter()
    for n in (graph_view or {}).get("nodes", []):
        if n.get("layer") == "changed" and n.get("path"):
            parts = n["path"].split("/")
            counts["/".join(parts[:2]) if len(parts) > 2 else "/".join(parts[:-1]) or default] += 1
    return counts.most_common(1)[0][0] if counts else default


async def _load(db: AsyncSession) -> list[dict[str, Any]]:
    rows = (await db.execute(
        select(Analysis, Push, Repo, SessionSignals)
        .join(Push, Push.id == Analysis.push_id).join(Repo, Repo.id == Push.repo_id)
        .join(SessionSignals, SessionSignals.analysis_id == Analysis.id)
        .where(Analysis.status == "done").order_by(Analysis.id)
    )).all()
    out = []
    latest: dict[str, int] = {}  # one conversation pushed several times counts once: its latest analysis wins
    for analysis, _push, _repo, sig in rows:
        latest[(sig.signals or {}).get("session_key") or f"analysis-{analysis.id}"] = analysis.id
    keep = set(latest.values())
    drivers: dict[int, Counter[str]] = defaultdict(Counter)
    for aid, driver, n in (await db.execute(
        select(FunctionReason.analysis_id, FunctionReason.driver, func.count()).group_by(FunctionReason.analysis_id, FunctionReason.driver)
    )).all():
        drivers[aid][driver] = n
    for analysis, push, repo, sig in rows:
        if analysis.id not in keep:
            continue
        decisions = (await db.execute(
            select(Decision).where(Decision.analysis_id == analysis.id).order_by(Decision.turn)
        )).scalars().all()
        pr = (await db.execute(
            select(PullRequest).join(PRAnalysis, PRAnalysis.pr_id == PullRequest.id)
            .where(PRAnalysis.analysis_id == analysis.id)
        )).scalars().first()
        when = (push.received_at or analysis.created_at).date()
        out.append({
            "analysis": analysis, "push": push, "repo": repo, "signals": sig.signals or {}, "steering": sig.steering or {},
            "decisions": decisions, "pr": pr, "when": when,
            "facts": analysis.facts or {}, "model": analysis.llm_model, "drivers": drivers[analysis.id],
            "area": _area(analysis.graph_view, repo.name),
            "number": pr.number if pr else 90000 + analysis.id,
            "dev": "dev-" + hashlib.sha1(f"{repo.owner}/{repo.name}:{push.branch}".encode()).hexdigest()[:4],
            "session": "s-" + analysis.public_id[:4],
        })
    return out


load_sessions = _load  # the same rows, for the metrics module and the dashboard routers


async def rollup_measured() -> dict[str, int]:
    async with session_scope() as db:
        team = await db.get(Team, settings.DASHBOARD_TEAM_ID)
        if team is None:  # allow a clean (unseeded) DB to store measured rollups with zero sample rows
            team = Team(
                id=settings.DASHBOARD_TEAM_ID, name=settings.DASHBOARD_TEAM_ID.title(), position=0,
                prs=0, prs_delta="0%", attempts=0.0, attempts_delta="0", overrules=0.0, thin=0, unsupported=0,
                funnel_total=0, funnel_first=0, funnel_second_agent=0, funnel_second_thin=0,
                funnel_third_agent=0, funnel_third_thin=0,
            )
            db.add(team)
            await db.flush()
        # Open measured candidates are rebuilt each run. A candidate someone already approved or rejected is kept.
        open_ids = select(GovCandidate.id).where(GovCandidate.source == "measured", GovCandidate.status == "open")
        await db.execute(delete(GovEvidence).where(GovEvidence.candidate_id.in_(open_ids)))
        await db.execute(delete(GovCandidate).where(GovCandidate.source == "measured", GovCandidate.status == "open"))
        for model in (GovSkillRule, TeamPR):
            await db.execute(delete(model).where(model.source == "measured"))
        await db.flush()
        decided = set((await db.execute(
            select(GovCandidate.id).where(GovCandidate.source == "measured")
        )).scalars())

        data = await _load(db)
        today_week = _monday(max((d["when"] for d in data), default=date.today()))
        weeks = [today_week - timedelta(weeks=7 - i) for i in range(8)]
        used_numbers: set[int] = set()
        sample_numbers = set((await db.execute(select(TeamPR.number).where(TeamPR.source == "sample"))).scalars())

        # ---- one team PR row per measured session
        for d in data:
            a, sig, decs = d["analysis"], d["signals"], d["decisions"]
            human = [x for x in decs if x.actor == "human"]
            title = (d["pr"].title if d["pr"] and d["pr"].title else (a.summary or "Agent session"))[:90]
            # A real PR number that a sample row already uses would break the unique key. The row then takes a
            # number from the analysis id, and its link (public_id) still goes to the right page.
            number = d["number"] if d["number"] not in sample_numbers | used_numbers else 90000 + a.id
            used_numbers.add(number)
            db.add(TeamPR(
                number=number, public_id=a.public_id, team_id=team.id, title=title, area=d["area"],
                week_start=_monday(d["when"]), agent=AGENT_LABEL.get(sig.get("agent", ""), sig.get("agent") or "Agent"),
                agent_decisions=sum(1 for x in decs if x.actor == "agent"), human_decisions=len(human),
                overrules=sum(1 for x in human if x.kind in OVERRIDE_KINDS), attempts=float(sig.get("attempts", 1)),
                flags=[f["flag"] for f in sig.get("flags", [])], source="measured",
            ))

        # ---- policy candidates from repeated human overrides
        overrides = []
        for d in data:
            for x in d["decisions"]:
                if x.actor == "human" and x.statement and x.kind in OVERRIDE_KINDS | {"requirement"}:
                    overrides.append({"d": d, "x": x, "statement": x.statement, "type": x.type})
        n_candidates = 0
        for members in cluster(overrides):
            sessions = {m["d"]["analysis"].id for m in members}
            if len(sessions) < settings.CANDIDATE_MIN_SESSIONS:
                continue
            anchor = min(m["x"].id for m in members)  # stable while new decisions arrive
            cid = f"cm{anchor}"
            if cid in decided:
                continue
            n_candidates += 1
            statement = Counter(m["statement"] for m in members).most_common(1)[0][0]
            first = min(m["d"]["when"] for m in members)
            trend = [sum(1 for m in members if _monday(m["d"]["when"]) == w) for w in weeks]
            db.add(GovCandidate(
                id=cid, pid=f"P-M{anchor}", statement=statement[:300], type=members[0]["type"],
                sessions=len(sessions), teams=1, developers=len({m["d"]["dev"] for m in members}), trend=trend,
                per_hundred=round(100 * len(sessions) / max(len(data), 1)),
                match="a human override with a matching statement, found in session decisions",
                scope="repo", enforcement="check", owner="@platform", expires=date.today() + timedelta(days=180),
                first_seen=first, status="open", source="measured",
            ))
            await db.flush()
            for n, m in enumerate(sorted(members, key=lambda m: m["x"].id)[:6]):
                d, x = m["d"], m["x"]
                db.add(GovEvidence(
                    id=f"em{x.id}", candidate_id=cid, position=n, session=d["session"], pr=f"#{d['number']}",
                    team=team.name, dev=d["dev"], turn=x.turn, kind=x.kind, occurred_on=d["when"],
                    proposal=x.proposal, choice=x.choice, quote=x.quote, source="measured",
                    public_id=d["analysis"].public_id,
                ))

        # ---- steering rule adherence
        counts: dict[tuple[str, str], dict[str, Any]] = {}
        for d in data:
            rules = {r["id"]: r for r in d["steering"].get("rules", [])}
            for x in d["decisions"]:
                if x.rule_id in rules and x.rule_followed is not None:
                    r = rules[x.rule_id]
                    c = counts.setdefault(
                        (r["source"], r["text"]),
                        {"followed": 0, "violated": 0, "trend": defaultdict(int), "pr": "", "turn": 0, "public_id": None},
                    )
                    if x.rule_followed:
                        c["followed"] += 1
                    else:
                        c["violated"] += 1
                        c["trend"][_monday(d["when"])] += 1
                        c["pr"], c["turn"], c["public_id"] = f"#{d['number']}", x.turn, d["analysis"].public_id
        for pos, ((source, text), c) in enumerate(sorted(counts.items(), key=lambda kv: -kv[1]["violated"])):
            db.add(GovSkillRule(
                id="rm" + hashlib.sha1(text.encode()).hexdigest()[:8], position=100 + pos, text=text[:280], skill=source,
                followed=c["followed"], violated=c["violated"], trend=[c["trend"].get(w, 0) for w in weeks],
                latest_pr=c["pr"] or "-", latest_turn=c["turn"], source="measured", latest_public_id=c["public_id"],
            ))
        return {"sessions": len(data), "candidates": n_candidates, "rules": len(counts)}


async def measured_summary(db: AsyncSession) -> dict[str, Any]:
    """Live numbers for the executive page, straight from the decisions table."""
    data = await _load(db)
    decs = [x for d in data for x in d["decisions"]]
    human = [x for x in decs if x.actor == "human"]
    with_rule = [x for x in decs if x.rule_followed is not None]
    tools: Counter[str] = Counter()
    tokens = 0
    for d in data:
        for name, row in d["signals"].get("tool_stats", {}).items():
            tools[name] += row.get("calls", 0)
            tokens += row.get("tokens", 0)
    return {
        "sessions": len(data),
        "decisions": len(decs),
        "human_decisions": len(human),
        "human_kinds": dict(Counter(x.kind for x in human)),
        "adherence": round(100 * sum(1 for x in with_rule if x.rule_followed) / len(with_rule)) if with_rule else None,
        "rule_checks": len(with_rule),
        "overrides_per_100": round(100 * sum(1 for x in human if x.kind in OVERRIDE_KINDS) / len(data)) if data else None,
        "tool_calls": sum(tools.values()),
        "tokens": tokens,
        "flags": dict(Counter(f["flag"] for d in data for f in d["signals"].get("flags", []))),
    }
