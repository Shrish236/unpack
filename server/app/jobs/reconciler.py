"""The poller (server design §3, revised): one sweep per interval checks every active branch's pull requests
and queues the posts that are pending. There are no webhooks.

Per repository with pending work there is one conditional call (`GET /repos/{o}/{r}/pulls`, ETag). A 304
costs no rate-limit budget and the stored list is reused. Compare results are cached on the pull request,
so an unchanged pair of commits is never compared twice.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
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

ACTIVE_STATUSES = ("waiting_for_pr", "linked")
PUBLISH_WAIT_SECONDS = 600  # wait this long for GitHub to catch up with a push before using an older analysis

# None = never synced. monotonic() counts from boot, so 0.0 would wrongly read as recent on a young host.
_last_installation_sync: float | None = None


@dataclass
class Target:
    analysis_id: int
    mode: str  # analysis | out_of_date
    banner_override: dict[str, str] | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def raw_from_pr(pr: PullRequest) -> dict[str, Any]:
    """The pull request as GitHub lists it, rebuilt from the stored row (used when the list is unchanged)."""
    return {
        "number": pr.number,
        "title": pr.title,
        "html_url": pr.html_url,
        "head": {"sha": pr.head_sha, "ref": pr.head_ref},
        "base": {"ref": pr.base_ref},
    }


def decide(
    *,
    decision: dict[str, Any] | None,
    pr_head: str,
    latest_id: int,
    latest_status: str,
    latest_head: str,
    done_by_head: dict[str, int],
    age_seconds: float,
    latest_short: str,
) -> Target | str | None:
    """Maps a compare decision to what to post. Pure, so the rules can be tested directly.

    `decision` is the cached compare result {"status", "behind_by", "ancestor"} or None when the PR head
    is already known to be one of our analyses.
    """
    if pr_head == latest_head:
        return Target(latest_id, "analysis") if latest_status in ("done", "failed") else "wait"
    if pr_head in done_by_head:
        return Target(done_by_head[pr_head], "analysis")
    if decision is None:
        return "wait"
    status = decision["status"]
    if status == "ahead":  # our push is not on GitHub yet
        if age_seconds < PUBLISH_WAIT_SECONDS:
            return "wait"
        ancestor = decision.get("ancestor")
        if ancestor:  # design §3.3: the newest analysis that is an ancestor of the PR head
            aid, head = ancestor
            return Target(aid, "analysis", {
                "kind": "partial_coverage",
                "message": f"Covers up to {head[:7]}; the newest push is not on GitHub yet.",
            })
        return None
    if status == "behind":  # commits were pushed without the hook
        n = decision["behind_by"]
        noun = "commit" if n == 1 else "commits"
        return Target(latest_id, "analysis", {
            "kind": "partial_coverage",
            "message": f"Covers up to {latest_short}; {n} newer {noun} were not analysed.",
        })
    if status == "diverged":
        return Target(latest_id, "out_of_date")
    if status == "identical":
        return Target(latest_id, "analysis")
    return None


async def reconcile_once() -> int:
    """One sweep: installation sync when due, then every repository with pending posts. Returns repos swept."""
    await _maybe_sync_installations()
    async with session_scope() as session:
        repo_ids = (await session.execute(
            select(TrackedBranch.repo_id).where(TrackedBranch.status.in_(ACTIVE_STATUSES)).distinct()
        )).scalars().all()
    gate = asyncio.Semaphore(max(settings.RECONCILE_CONCURRENCY, 1))

    async def one(repo_id: int) -> None:
        async with gate:
            try:
                await sweep_repo(repo_id)
            except Exception as exc:  # one repository must not stop the others; the next sweep retries it
                log.warning("sweep of repository %s failed: %s", repo_id, type(exc).__name__)
                async with session_scope() as session:
                    await session.execute(text(
                        "UPDATE tracked_branches SET last_error = :e WHERE repo_id = :r"
                    ), {"e": f"{type(exc).__name__}: {str(exc)[:400]}", "r": repo_id})

    await asyncio.gather(*(one(rid) for rid in repo_ids))
    return len(repo_ids)


async def sweep_repo(repo_id: int) -> None:
    svc = get_github()
    async with session_scope() as session:
        repo = await session.get(Repo, repo_id)
        if repo is None or repo.status != "active" or repo.installation_id is None:
            return
        token = await svc.installation_token(repo.installation_id)
        changed, fresh, etag = await gh_prs.list_open_pulls_conditional(
            svc, token, repo.owner, repo.name, repo.pulls_etag)
        if changed:
            repo.pulls_etag = etag
            stored = (await session.execute(select(PullRequest).where(
                PullRequest.repo_id == repo.id, PullRequest.state == "open"))).scalars().all()
            open_numbers = {raw["number"] for raw in fresh}
            for raw in fresh:
                await upsert_pr(session, repo, raw)
            for pr in stored:
                if pr.number not in open_numbers:
                    await _settle_closed(svc, token, repo, pr)
            pulls = fresh
        else:
            stored = (await session.execute(select(PullRequest).where(
                PullRequest.repo_id == repo.id, PullRequest.state == "open"))).scalars().all()
            pulls = [raw_from_pr(pr) for pr in stored]

        # Every active branch, not only those with a post pending: a PR that closes or merges must be noticed.
        pending = (await session.execute(select(TrackedBranch).where(
            TrackedBranch.repo_id == repo.id, TrackedBranch.status.in_(ACTIVE_STATUSES),
        ))).scalars().all()
        for tb in pending:
            await sweep_branch(session, svc, token, repo, tb, pulls)


async def upsert_pr(session: Any, repo: Repo, raw: dict[str, Any]) -> PullRequest:
    pr = (await session.execute(select(PullRequest).where(
        PullRequest.repo_id == repo.id, PullRequest.number == raw["number"]))).scalar_one_or_none()
    if pr is None:
        pr = PullRequest(repo_id=repo.id, number=raw["number"], head_ref=raw["head"]["ref"],
                         head_sha=raw["head"]["sha"], base_ref=raw["base"]["ref"])
        session.add(pr)
    pr.head_ref = raw["head"]["ref"]
    pr.head_sha = raw["head"]["sha"]
    pr.base_ref = raw["base"]["ref"]
    pr.title = raw.get("title")
    pr.html_url = raw.get("html_url")
    pr.state = "open"
    return pr


async def _settle_closed(svc: Any, token: str, repo: Repo, pr: PullRequest) -> None:
    """A stored open PR is missing from a fresh list: find out whether it was merged or closed."""
    try:
        raw = await gh_prs.get_pr(svc, token, repo.owner, repo.name, pr.number)
    except GitHubError:
        return
    if raw.get("state") == "closed":
        pr.state = "merged" if raw.get("merged_at") else "closed"


async def sweep_branch(session: Any, svc: Any, token: str, repo: Repo, tb: TrackedBranch,
                       pulls: list[dict[str, Any]]) -> None:
    latest_push = await session.get(Push, tb.latest_push_id) if tb.latest_push_id else None
    if latest_push is None:
        return
    latest = (await session.execute(select(Analysis).where(Analysis.push_id == latest_push.id))).scalar_one_or_none()
    if latest is None:
        return
    tb.last_checked_at = _now()
    tb.check_count = (tb.check_count or 0) + 1
    tb.last_error = None
    age = (_now() - latest_push.received_at).total_seconds() if latest_push.received_at else 0.0
    branch_prs = [raw for raw in pulls if raw["head"]["ref"] == tb.branch]

    if not branch_prs:
        linked = (await session.execute(select(PullRequest).where(PullRequest.tracked_branch_id == tb.id))).scalars().all()
        if linked and all(pr.state != "open" for pr in linked):
            tb.status = "closed_recently"
            tb.needs_publish = False
            return
        if age > settings.PR_WAIT_DAYS * 86400:
            tb.status = "abandoned"  # held for PR_WAIT_DAYS; posting is on demand from now on
            tb.needs_publish = False
        return

    done_rows = (await session.execute(
        select(Analysis.id, Push.head_sha).join(Push, Push.id == Analysis.push_id).where(
            Push.repo_id == repo.id, Push.branch == tb.branch, Analysis.status == "done")
    )).all()
    done_by_head = {head: aid for aid, head in done_rows}

    waiting = False
    for raw in branch_prs:
        pr = await upsert_pr(session, repo, raw)
        pr.tracked_branch_id = tb.id
        await session.flush()
        decision = await _compare_decision(session, svc, token, repo, pr, latest, latest_push, done_by_head, age)
        target = decide(
            decision=decision,
            pr_head=pr.head_sha,
            latest_id=latest.id,
            latest_status=latest.status,
            latest_head=latest_push.head_sha,
            done_by_head=done_by_head,
            age_seconds=age,
            latest_short=latest_push.head_sha[:7],
        )
        if target == "wait":
            waiting = True
        elif isinstance(target, Target):
            await _enqueue_publish(session, pr.id, target)
    tb.status = "linked"
    open_linked = (await session.execute(select(PullRequest).where(
        PullRequest.tracked_branch_id == tb.id, PullRequest.state == "open"))).scalars().all()
    tb.needs_publish = waiting or any(pr.last_published_analysis_id != latest.id for pr in open_linked)


async def _compare_decision(session: Any, svc: Any, token: str, repo: Repo, pr: PullRequest,
                            latest: Analysis, latest_push: Push, done_by_head: dict[str, int],
                            age: float) -> dict[str, Any] | None:
    """The compare result for this PR head and our latest head, cached on the pull request."""
    pr_head = pr.head_sha
    if pr_head == latest_push.head_sha or pr_head in done_by_head:
        return None
    key = f"{pr_head}>{latest_push.head_sha}"
    cache = pr.compare_cache or {}
    if cache.get("key") == key:
        decision = dict(cache["result"])
    else:
        cmp = await gh_prs.compare(svc, token, repo.owner, repo.name, pr_head, latest_push.head_sha)
        decision = {"status": cmp.status, "behind_by": cmp.behind_by, "ancestor": None, "ancestor_checked": False}
    if decision["status"] == "ahead" and age >= PUBLISH_WAIT_SECONDS and not decision.get("ancestor_checked"):
        decision["ancestor"] = await _ancestor(svc, token, repo, pr_head, latest_push.head_sha, done_by_head)
        decision["ancestor_checked"] = True
    pr.compare_cache = {"key": key, "result": decision}
    return decision


async def _ancestor(svc: Any, token: str, repo: Repo, pr_head: str, latest_head: str,
                    done_by_head: dict[str, int]) -> list[Any] | None:
    """Newest done analysis whose head is contained in the PR head (design §3.3)."""
    for head, aid in sorted(done_by_head.items(), key=lambda item: -item[1]):
        if head == latest_head:
            continue
        result = await gh_prs.compare(svc, token, repo.owner, repo.name, head, pr_head)
        if result.status == "ahead":
            return [aid, head]
    return None


async def _enqueue_publish(session: Any, pr_id: int, target: Target) -> None:
    payload = {"pr_id": pr_id, "analysis_id": target.analysis_id, "mode": target.mode}
    if target.banner_override:
        payload["banner_override"] = target.banner_override
    await enqueue(session, "publish_comment", payload, dedupe_key=f"publish:pr:{pr_id}")
    await session.execute(text(
        "INSERT INTO pr_analyses (pr_id, analysis_id, linked_at) VALUES (:p, :a, now()) ON CONFLICT DO NOTHING"
    ), {"p": pr_id, "a": target.analysis_id})


async def _maybe_sync_installations() -> None:
    """Keeps repo.installation_id and status in step with the App's installations (replaces webhooks)."""
    global _last_installation_sync
    if _last_installation_sync is not None and time.monotonic() - _last_installation_sync < settings.INSTALLATION_SYNC_SECONDS:
        return
    _last_installation_sync = time.monotonic()
    try:
        await sync_installations()
    except Exception as exc:
        # Retry in a minute rather than on every sweep: a failing sync must not hammer GitHub.
        _last_installation_sync = time.monotonic() - settings.INSTALLATION_SYNC_SECONDS + 60
        log.warning("installation sync failed: %s", type(exc).__name__)


async def sync_installations() -> None:
    svc = get_github()
    installs = await gh_prs.list_installations(svc)
    owned: dict[str, int] = {}
    for inst in installs:
        for item in await gh_prs.installation_repositories(svc, inst["id"]):
            owned[item["full_name"].lower()] = inst["id"]
    async with session_scope() as session:
        for repo in (await session.execute(select(Repo))).scalars().all():
            key = f"{repo.owner}/{repo.name}".lower()
            if repo.status == "disabled":
                continue
            if key in owned:
                repo.installation_id = owned[key]
                repo.status = "active"
            elif repo.installation_id is not None or repo.status == "active":
                repo.installation_id = None
                repo.status = "app_missing"
