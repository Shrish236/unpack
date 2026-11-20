"""Governance inbox: candidates, published policies, skill rules and history. Dummy data until the pipeline runs.

Every decision here (approve, reject, retire, revise) writes to the database and returns the whole inbox,
so the page can refresh from one response. Any logged-in viewer can act; per-role permissions come later.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import viewer
from ..errors import ApiError
from ..models import GovCandidate, GovEvidence, GovHistory, GovPolicy, GovSkillRule

router = APIRouter(prefix="/api/governance", dependencies=[Depends(viewer)])

ROLE = "Tech lead (you)"
# Placeholder mapping until a team and repo picker exists. The mock used the same names.
SCOPE_NAME = {"org": "Org", "team": "Payments", "repo": "payments-service"}
TREND_ON_REVISE = [1, 1, 2, 1, 2, 2, 3, 3]

Scope = Literal["repo", "team", "org"]
Enforcement = Literal["advice", "check", "gate"]


class ApproveIn(BaseModel):
    statement: str = Field(min_length=1, max_length=300)
    scope: Scope
    enforcement: Enforcement
    owner: str = Field(pattern=r"^@[A-Za-z0-9][A-Za-z0-9_-]*$")
    expires: date


class RejectIn(BaseModel):
    reason: str = Field(default="", max_length=1000)


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _evidence_out(e: GovEvidence) -> dict[str, Any]:
    return {
        "id": e.id, "public_id": e.public_id, "session": e.session, "pr": e.pr, "team": e.team, "dev": e.dev, "turn": e.turn,
        "kind": e.kind, "proposal": e.proposal, "choice": e.choice, "quote": e.quote, "when": e.occurred_on.isoformat(),
        "source": e.source,
    }


async def _state(db: AsyncSession) -> dict[str, Any]:
    candidates = (await db.execute(
        select(GovCandidate).where(GovCandidate.status == "open")
        .order_by((GovCandidate.source == "measured").desc(), GovCandidate.developers.desc(), GovCandidate.sessions.desc())
    )).scalars().all()
    policies = (await db.execute(
        select(GovPolicy).where(GovPolicy.status == "active").order_by(GovPolicy.id.desc())
    )).scalars().all()
    rules = (await db.execute(select(GovSkillRule).order_by((GovSkillRule.source == "measured").desc(), GovSkillRule.position))).scalars().all()
    history = (await db.execute(select(GovHistory).order_by(GovHistory.seq.desc()))).scalars().all()
    evidence = (await db.execute(select(GovEvidence).order_by(GovEvidence.position))).scalars().all()

    by_candidate: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_policy: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in evidence:
        if e.candidate_id:
            by_candidate[e.candidate_id].append(_evidence_out(e))
        if e.policy_id:
            by_policy[e.policy_id].append(_evidence_out(e))

    return {
        "today": _today().isoformat(),
        "candidates": [
            {
                "id": c.id, "pid": c.pid, "statement": c.statement, "type": c.type, "sessions": c.sessions,
                "teams": c.teams, "developers": c.developers, "trend": list(c.trend),
                "per_hundred": c.per_hundred, "match": c.match, "scope": c.scope, "enforcement": c.enforcement,
                "owner": c.owner, "expires": c.expires.isoformat(), "evidence": by_candidate[c.id], "source": c.source,
            }
            for c in candidates
        ],
        "policies": [
            {
                "id": p.id, "statement": p.statement, "type": p.type, "scope": p.scope, "scope_name": p.scope_name,
                "enforcement": p.enforcement, "owner": p.owner, "expires": p.expires.isoformat(),
                "adherence": p.adherence, "before": p.before, "after": p.after, "match": p.match,
                "recurrence": None if p.recurrence_sessions is None else {
                    "sessions": p.recurrence_sessions, "teams": p.recurrence_teams,
                    "developers": p.recurrence_developers, "evidence": by_policy[p.id],
                },
            }
            for p in policies
        ],
        "rules": [
            {
                "id": r.id, "text": r.text, "skill": r.skill, "followed": r.followed, "violated": r.violated,
                "trend": list(r.trend), "latest_pr": r.latest_pr, "latest_turn": r.latest_turn, "latest_public_id": r.latest_public_id, "source": r.source,
            }
            for r in rules
        ],
        "history": [
            {"id": h.id, "statement": h.statement, "outcome": h.outcome, "role": h.role,
             "when": h.occurred_on.isoformat(), "why": h.why}
            for h in history
        ],
    }


async def _open_candidate(db: AsyncSession, candidate_id: str) -> GovCandidate:
    candidate = await db.get(GovCandidate, candidate_id)
    if candidate is None:
        raise ApiError(404, "not_found", "no such candidate")
    if candidate.status != "open":
        raise ApiError(409, "not_open", f"the candidate is already {candidate.status}")
    return candidate


async def _active_policy(db: AsyncSession, policy_id: str) -> GovPolicy:
    policy = await db.get(GovPolicy, policy_id)
    if policy is None or policy.status != "active":
        raise ApiError(404, "not_found", "no such active policy")
    return policy


@router.get("")
async def governance_inbox(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return await _state(db)


@router.post("/candidates/{candidate_id}/approve")
async def approve(candidate_id: str, body: ApproveIn, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    candidate = await _open_candidate(db, candidate_id)
    today = _today()
    statement = body.statement.strip()
    if not statement:
        raise ApiError(400, "invalid_payload", "statement: must not be blank")
    if body.expires < today:
        raise ApiError(400, "invalid_payload", "expires: must be today or later")
    if await db.get(GovPolicy, candidate.pid) is not None:
        raise ApiError(409, "policy_exists", f"policy {candidate.pid} already exists")

    db.add(GovPolicy(
        id=candidate.pid, statement=statement, type=candidate.type, scope=body.scope,
        scope_name=SCOPE_NAME[body.scope], enforcement=body.enforcement, owner=body.owner, expires=body.expires,
        adherence=None, before=candidate.per_hundred, after=None, match=candidate.match,
        status="active", published_on=today,
    ))
    candidate.status = "approved"
    candidate.decided_at = datetime.now(timezone.utc)
    db.add(GovHistory(
        id=f"h-{candidate.pid}", statement=statement, outcome="approved", role=ROLE, occurred_on=today,
        why=f"{candidate.sessions} sessions across {candidate.teams} teams, {candidate.developers} developers.",
    ))
    await db.flush()
    return await _state(db)


@router.post("/candidates/{candidate_id}/reject")
async def reject(candidate_id: str, body: RejectIn | None = None, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    candidate = await _open_candidate(db, candidate_id)
    reason = body.reason.strip() if body else ""
    candidate.status = "rejected"
    candidate.decided_at = datetime.now(timezone.utc)
    db.add(GovHistory(
        id=f"h-{candidate.pid}", statement=candidate.statement, outcome="rejected", role=ROLE, occurred_on=_today(),
        why=reason or "No reason given.",
    ))
    await db.flush()
    return await _state(db)


@router.post("/policies/{policy_id}/retire")
async def retire(policy_id: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    policy = await _active_policy(db, policy_id)
    policy.status = "retired"
    db.add(GovHistory(
        id=f"h-{policy.id}-r", statement=policy.statement, outcome="expired", role="Policy owner",
        occurred_on=_today(), why="Retired: the override kept recurring after the policy.",
    ))
    await db.flush()
    return await _state(db)


@router.post("/policies/{policy_id}/revise")
async def revise(policy_id: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Reopens a policy that is still being overridden as a candidate, so its statement can be edited."""
    policy = await _active_policy(db, policy_id)
    if policy.recurrence_sessions is None:
        raise ApiError(409, "no_recurrence", "only a policy that is still being overridden can be revised")

    candidate_id, pid = f"c-{policy.id}", f"{policy.id}b"
    clash = (await db.execute(select(GovCandidate.id).where(
        (GovCandidate.id == candidate_id) | (GovCandidate.pid == pid)))).first()
    if clash is not None:
        raise ApiError(409, "candidate_exists", f"a candidate for {policy.id} is already in the inbox")

    db.add(GovCandidate(
        id=candidate_id, pid=pid, statement=policy.statement, type=policy.type,
        sessions=policy.recurrence_sessions, teams=policy.recurrence_teams or 0,
        developers=policy.recurrence_developers or 0, trend=TREND_ON_REVISE, per_hundred=policy.after or 0,
        match=policy.match, scope=policy.scope, enforcement=policy.enforcement, owner=policy.owner,
        expires=policy.expires, first_seen=_today(), status="open",
    ))
    await db.flush()
    evidence = (await db.execute(
        select(GovEvidence).where(GovEvidence.policy_id == policy.id).order_by(GovEvidence.position)
    )).scalars().all()
    for e in evidence:
        db.add(GovEvidence(
            id=f"{e.id}-{candidate_id}", candidate_id=candidate_id, policy_id=None, position=e.position,
            session=e.session, pr=e.pr, team=e.team, dev=e.dev, turn=e.turn, kind=e.kind,
            occurred_on=e.occurred_on, proposal=e.proposal, choice=e.choice, quote=e.quote,
        ))
    policy.status = "revised"
    await db.flush()
    return await _state(db)
