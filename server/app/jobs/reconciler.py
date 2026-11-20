"""Branch reconciler: finds the pull request for each tracked branch and keeps its comment current (server design §3)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, text

from ..config import settings
from ..db import session_scope
from ..github import prs as gh_prs
from ..github.service import GitHubError
from ..models import Analysis, Push, PullRequest, Repo, TrackedBranch
from ..services import get_github
from .queue import enqueue

log = logging.getLogger("unpack.reconciler")

ACTIVE_STATUSES = ("waiting_for_pr", "linked", "closed_recently")
PUBLISH_WAIT_SECONDS = 600  # wait this long for GitHub to catch up with our push
LINKED_CHECK_SECONDS = 120


def backoff_seconds(age_seconds: float) -> float | None:
    """Design §3.4. None means stop tracking (abandoned)."""
    if age_seconds < 600:
        return 30
    if age_seconds < 3600:
        return 120
    if age_seconds < 86400:
        return 600
    if age_seconds < 7 * 86400:
        return 3600
    return None


@dataclass
class Target:
    analysis_id: int
    mode: str  # analysis | out_of_date
    banner_override: dict[str, str] | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def reconcile_once() -> int:
    """One tick: claim due branches and check each. Returns the number checked."""
    async with session_scope() as session:
        ids = (await session.execute(text(
            """
            UPDATE tracked_branches SET next_check_at = now() + interval '60 seconds', check_count = check_count + 1
            WHERE id IN (
                SELECT id FROM tracked_branches
                WHERE status IN ('waiting_for_pr', 'linked', 'closed_recently') AND next_check_at <= now()
                ORDER BY next_check_at
                FOR UPDATE SKIP LOCKED
                LIMIT 50
            )
            RETURNING id
            """
        ))).scalars().all()
    gate = asyncio.Semaphore(max(settings.RECONCILE_CONCURRENCY, 1))

    async def check_one(tid: int) -> None:
        async with gate:
            try:
                await check_branch(int(tid))
            except Exception as exc:  # one bad branch must not stop the others
                log.warning("branch %s check failed: %s", tid, type(exc).__name__)
                async with session_scope() as session:
                    row = await session.get(TrackedBranch, tid)
                    if row is not None:
                        row.last_error = f"{type(exc).__name__}: {str(exc)[:400]}"
                        row.next_check_at = _now() + timedelta(seconds=120)

    await asyncio.gather(*(check_one(tid) for tid in ids))
    return len(ids)


def choose_target(
    *,
    pr_head: str,
    latest: Analysis,
    latest_head: str,
    done_by_head: dict[str, int],
    compare_result: Any,
    latest_age_seconds: float,
    latest_short: str,
) -> Target | str | None:
    """Design §3.3. Returns a Target to publish, "wait", or None for nothing to publish."""
    if pr_head == latest_head:
        if latest.status in ("done", "failed"):
            return Target(latest.id, "analysis")
        return "wait"
    if pr_head in done_by_head:
        return Target(done_by_head[pr_head], "analysis")
    status = compare_result.status
    if status == "ahead":  # our push is not on GitHub yet
        if latest_age_seconds < PUBLISH_WAIT_SECONDS:
            return "wait"
        return "ancestor"  # design §3.3: fall back to the newest analysis that is an ancestor of the PR head
    if status == "behind":  # commits were pushed without the hook
        n = compare_result.behind_by
        noun = "commit" if n == 1 else "commits"
        return Target(latest.id, "analysis", {
            "kind": "partial_coverage",
            "message": f"Covers up to {latest_short}; {n} newer {noun} were not analysed.",
        })
    if status == "diverged":
        return Target(latest.id, "out_of_date")
    if status == "identical":
        return Target(latest.id, "analysis")
    return None


async def check_branch(tracked_id: int) -> None:
    svc = get_github()
    async with session_scope() as session:
        row = await session.get(TrackedBranch, tracked_id)
        if row is None or row.status not in ACTIVE_STATUSES:
            return
        repo = await session.get(Repo, row.repo_id)
        latest_push = await session.get(Push, row.latest_push_id) if row.latest_push_id else None
        if latest_push is None:
            return
        latest = (await session.execute(select(Analysis).where(Analysis.push_id == latest_push.id))).scalar_one_or_none()
        done_rows = (await session.execute(
            select(Analysis.id, Push.head_sha)
            .join(Push, Push.id == Analysis.push_id)
            .where(Push.repo_id == row.repo_id, Push.branch == row.branch, Analysis.status == "done")
        )).all()
        done_by_head = {head: aid for aid, head in done_rows}
        snapshot = {
            "tracked_id": row.id, "branch": row.branch, "repo_id": repo.id, "owner": repo.owner,
            "name": repo.name, "installation_id": repo.installation_id, "repo_status": repo.status,
            "latest_head": row.latest_head_sha, "latest_id": latest.id if latest else None,
            "latest_status": latest.status if latest else None,
            "latest_received": latest_push.received_at, "latest_short": latest_push.head_sha[:7],
        }

    now = _now()
    received = snapshot["latest_received"]
    age = (now - received).total_seconds() if received else 0.0

    if snapshot["repo_status"] != "active" or snapshot["installation_id"] is None:
        await _set_next(tracked_id, now + timedelta(hours=1), status=None)
        return
    if snapshot["latest_id"] is None:
        await _set_next(tracked_id, now + timedelta(seconds=30))
        return
    if snapshot["latest_status"] in ("queued", "running"):
        await _set_next(tracked_id, now + timedelta(seconds=15))
        return

    token = await svc.installation_token(snapshot["installation_id"])
    owner, name, branch = snapshot["owner"], snapshot["name"], snapshot["branch"]
    open_prs = await gh_prs.list_open_prs_for_head(svc, token, owner, name, branch)

    if not open_prs:
        await _handle_no_pr(tracked_id, snapshot, token, age, now)
        return

    scheduled_targets: list[Target | str | None] = []
    for raw in open_prs:
        pr_head = raw["head"]["sha"]
        compare_result = None
        if pr_head != snapshot["latest_head"] and pr_head not in done_by_head:
            compare_result = await gh_prs.compare(svc, token, owner, name, pr_head, snapshot["latest_head"])
        async with session_scope() as session:
            pr = (await session.execute(select(PullRequest).where(
                PullRequest.repo_id == snapshot["repo_id"], PullRequest.number == raw["number"]
            ))).scalar_one_or_none()
            if pr is None:
                pr = PullRequest(repo_id=snapshot["repo_id"], number=raw["number"], head_ref=branch,
                                 head_sha=pr_head, base_ref=raw["base"]["ref"])
                session.add(pr)
            pr.tracked_branch_id = snapshot["tracked_id"]
            pr.head_sha = pr_head
            pr.base_ref = raw["base"]["ref"]
            pr.title = raw.get("title")
            pr.html_url = raw.get("html_url")
            pr.state = "open"
            await session.flush()
            pr_id = pr.id
        target = choose_target(
            pr_head=pr_head,
            latest=await _load_latest(snapshot["latest_id"]),
            latest_head=snapshot["latest_head"],
            done_by_head=done_by_head,
            compare_result=compare_result if compare_result is not None else _same_head(),
            latest_age_seconds=age,
            latest_short=snapshot["latest_short"],
        )
        if target == "ancestor":
            target = await _ancestor_target(svc, token, owner, name, pr_head, snapshot, done_by_head)
        scheduled_targets.append(target)
        if isinstance(target, Target):
            await _enqueue_publish(pr_id, target)

    async with session_scope() as session:
        row = await session.get(TrackedBranch, tracked_id)
        row.status = "linked"
        row.last_checked_at = _now()
        row.last_error = None
        wait = any(t == "wait" for t in scheduled_targets)
        row.next_check_at = _now() + timedelta(seconds=15 if wait else LINKED_CHECK_SECONDS)
        # Design §4: needs_publish stays true until every open PR shows the latest analysis.
        open_prs = (await session.execute(select(PullRequest).where(
            PullRequest.tracked_branch_id == tracked_id, PullRequest.state == "open"))).scalars().all()
        row.needs_publish = any(pr.last_published_analysis_id != snapshot["latest_id"] for pr in open_prs)


async def _ancestor_target(svc: Any, token: str, owner: str, name: str, pr_head: str,
                           snapshot: dict[str, Any], done_by_head: dict[str, int]) -> Target | None:
    """Newest done analysis whose head is an ancestor of the PR head (design §3.3, after 10 minutes)."""
    candidates = sorted(((head, aid) for head, aid in done_by_head.items()
                         if head != snapshot["latest_head"]), key=lambda item: -item[1])
    for head, aid in candidates:
        result = await gh_prs.compare(svc, token, owner, name, head, pr_head)
        if result.status == "ahead":  # the PR head contains this analysis's head
            return Target(aid, "analysis", {
                "kind": "partial_coverage",
                "message": f"Covers up to {head[:7]}; the newest push is not on GitHub yet.",
            })
    return None


@dataclass
class _Same:
    status: str = "identical"
    ahead_by: int = 0
    behind_by: int = 0


def _same_head() -> _Same:
    return _Same()


async def _load_latest(analysis_id: int | None) -> Analysis:
    async with session_scope() as session:
        analysis = await session.get(Analysis, analysis_id)
        session.expunge(analysis)
        return analysis


async def _enqueue_publish(pr_id: int, target: Target) -> None:
    payload = {"pr_id": pr_id, "analysis_id": target.analysis_id, "mode": target.mode}
    if target.banner_override:
        payload["banner_override"] = target.banner_override
    async with session_scope() as session:
        await enqueue(session, "publish_comment", payload, dedupe_key=f"publish:pr:{pr_id}")
        await session.execute(text(
            "INSERT INTO pr_analyses (pr_id, analysis_id, linked_at) VALUES (:p, :a, now()) "
            "ON CONFLICT DO NOTHING"
        ), {"p": pr_id, "a": target.analysis_id})


async def _handle_no_pr(tracked_id: int, snapshot: dict[str, Any], token: str, age: float, now: datetime) -> None:
    svc = get_github()
    async with session_scope() as session:
        linked = (await session.execute(select(PullRequest).where(
            PullRequest.tracked_branch_id == tracked_id, PullRequest.state == "open"
        ))).scalars().all()
        pr_numbers = [(pr.id, pr.number) for pr in linked]
    for pr_id, number in pr_numbers:
        try:
            raw = await gh_prs.get_pr(svc, token, snapshot["owner"], snapshot["name"], number)
        except GitHubError:
            continue
        if raw.get("state") == "closed":
            state = "merged" if raw.get("merged_at") else "closed"
            async with session_scope() as session:
                pr = await session.get(PullRequest, pr_id)
                pr.state = state

    if pr_numbers:
        status = "closed_recently"
    else:
        status = "waiting_for_pr"
    limit = settings.TRACK_MAX_DAYS * 86400
    delay = backoff_seconds(age)
    if age > limit or delay is None:
        await _set_next(tracked_id, now + timedelta(days=365), status="abandoned")
        return
    await _set_next(tracked_id, now + timedelta(seconds=delay), status=status)


async def _set_next(tracked_id: int, when: datetime, status: str | None = None) -> None:
    async with session_scope() as session:
        row = await session.get(TrackedBranch, tracked_id)
        row.next_check_at = when
        row.last_checked_at = _now()
        if status is not None:
            row.status = status
