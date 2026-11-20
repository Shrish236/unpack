"""publish_comment: create or update the one Unpack comment on a pull request (server design §3.5, §8.3)."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text

from ..config import settings
from ..db import session_scope
from ..github.comments import build_comment_body, create_comment, find_unpack_comment, update_comment
from ..models import Analysis, PullRequest, Render, Repo, TrackedBranch
from ..services import get_github


def _now_text() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _live_url(public_id: str) -> str:
    return f"{settings.UNPACK_BASE_URL.rstrip('/')}/a/{public_id}"


async def _image_url(session: Any, analysis_id: int) -> str | None:
    render = (await session.execute(
        select(Render)
        .where(Render.analysis_id == analysis_id, Render.status == "done")
        .order_by(Render.id.desc())
        .limit(1)
    )).scalar_one_or_none()
    if render is None:
        return None
    return f"{settings.UNPACK_BASE_URL.rstrip('/')}/img/{render.file_name}.png"


def build_body(
    analysis: Analysis,
    *,
    image_url: str | None,
    banner_override: dict[str, str] | None,
    short_sha: str,
    mode: str,
) -> str:
    if mode == "out_of_date":
        return build_comment_body(
            analysis_public_id=analysis.public_id,
            short_sha=short_sha,
            summary="",
            stats={"functions_changed": 0, "by_change": {}},
            not_reached=[],
            banner_message="Out of date: the branch changed after this analysis. Waiting for the next push.",
            image_url=None,
            live_url=_live_url(analysis.public_id),
            generated_at=_now_text(),
        )
    if analysis.status == "failed":
        return build_comment_body(
            analysis_public_id=analysis.public_id,
            short_sha=short_sha,
            summary="",
            stats={"functions_changed": 0, "by_change": {}},
            not_reached=[],
            banner_message=f"Analysis could not be completed ({analysis.error_code}). Open the live graph for details.",
            image_url=None,
            live_url=_live_url(analysis.public_id),
            generated_at=_now_text(),
        )
    banner_message = None
    if banner_override:
        banner_message = banner_override["message"]
    elif analysis.banner:
        banner_message = analysis.banner.get("message")
    not_reached = [f"{n['path']}::{n['label']}" for n in (analysis.graph_view or {}).get("nodes", [])
                   if n.get("layer") == "changed" and (n.get("test") or {}).get("label") == "none"]
    return build_comment_body(
        analysis_public_id=analysis.public_id,
        short_sha=short_sha,
        summary=analysis.summary or "",
        stats=analysis.stats or {},
        not_reached=not_reached,
        banner_message=banner_message,
        image_url=image_url,
        live_url=_live_url(analysis.public_id),
        generated_at=_now_text(),
    )


async def publish(pr_id: int, analysis_id: int, *, mode: str = "analysis",
                  banner_override: dict[str, str] | None = None) -> str:
    """Returns "published", "unchanged" or "skipped"."""
    svc = get_github()
    async with session_scope() as session:
        # One publish at a time per pull request.
        await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": pr_id})
        pr = await session.get(PullRequest, pr_id)
        analysis = await session.get(Analysis, analysis_id)
        if pr is None or analysis is None:
            return "skipped"
        repo = await session.get(Repo, pr.repo_id)
        if repo is None or repo.installation_id is None or repo.status != "active":
            return "skipped"
        image_url = await _image_url(session, analysis.id) if mode == "analysis" else None
        short_sha = (await _short_sha(session, analysis))
        body = build_body(analysis, image_url=image_url, banner_override=banner_override,
                          short_sha=short_sha, mode=mode)
        body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
        if pr.last_published_analysis_id == analysis.id and pr.last_body_hash == body_hash:
            return "unchanged"

        token = await svc.installation_token(repo.installation_id)
        comment: dict[str, Any] | None = None
        if pr.comment_id:
            comment = await update_comment(svc, token, repo.owner, repo.name, pr.comment_id, body)
        if comment is None:
            found = await find_unpack_comment(svc, token, repo.owner, repo.name, pr.number)
            if found:
                comment = await update_comment(svc, token, repo.owner, repo.name, found["id"], body) or found
            else:
                comment = await create_comment(svc, token, repo.owner, repo.name, pr.number, body)
        pr.comment_id = comment["id"]
        pr.comment_url = comment.get("html_url")
        if mode == "analysis":
            pr.last_published_analysis_id = analysis.id
        pr.last_body_hash = body_hash
        pr.last_published_at = datetime.now(timezone.utc)
        await _refresh_needs_publish(session, pr)
        return "published"


async def _refresh_needs_publish(session: Any, pr: PullRequest) -> None:
    """Design §4: needs_publish is false once every open PR on the branch shows the latest analysis."""
    if pr.tracked_branch_id is None:
        return
    tracked = await session.get(TrackedBranch, pr.tracked_branch_id)
    if tracked is None or tracked.latest_push_id is None:
        return
    latest = (await session.execute(select(Analysis.id).where(Analysis.push_id == tracked.latest_push_id))).scalar_one_or_none()
    open_prs = (await session.execute(select(PullRequest).where(
        PullRequest.tracked_branch_id == tracked.id, PullRequest.state == "open"))).scalars().all()
    tracked.needs_publish = any(p.last_published_analysis_id != latest for p in open_prs)


async def _short_sha(session: Any, analysis: Analysis) -> str:
    from ..models import Push

    push = await session.get(Push, analysis.push_id)
    return push.head_sha[:7] if push else "unknown"


async def publish_job(payload: dict[str, Any]) -> str:
    return await publish(
        int(payload["pr_id"]),
        int(payload["analysis_id"]),
        mode=payload.get("mode", "analysis"),
        banner_override=payload.get("banner_override"),
    )
