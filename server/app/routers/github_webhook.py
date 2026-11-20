"""GitHub App webhook (optional nudge) and the post-install setup page (server design §5.3)."""

from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import get_db
from ..errors import ApiError
from ..github import prs as gh_prs
from ..models import Repo, TrackedBranch, WebhookDelivery
from ..security import verify_webhook_signature
from ..services import get_github

router = APIRouter()


@router.post("/github/webhook")
async def webhook(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    if not settings.GITHUB_WEBHOOK_SECRET:
        raise ApiError(404, "not_found", "webhooks are disabled")
    body = await request.body()
    if not verify_webhook_signature(settings.GITHUB_WEBHOOK_SECRET, body, request.headers.get("x-hub-signature-256")):
        raise ApiError(401, "invalid_signature", "bad signature")
    delivery_id = request.headers.get("x-github-delivery", "")
    event = request.headers.get("x-github-event", "")
    if delivery_id:
        if await db.get(WebhookDelivery, delivery_id) is not None:
            return Response(status_code=204)
        db.add(WebhookDelivery(delivery_id=delivery_id, event=event))
        await db.flush()

    import json

    data: dict[str, Any] = json.loads(body or b"{}")
    if event == "pull_request":
        full = (data.get("repository") or {}).get("full_name", "")
        head_ref = ((data.get("pull_request") or {}).get("head") or {}).get("ref")
        owner, _, name = full.partition("/")
        repo = (await db.execute(select(Repo).where(
            Repo.owner == owner, Repo.name == name))).scalar_one_or_none()
        if repo is not None and head_ref:
            tracked = (await db.execute(select(TrackedBranch).where(
                TrackedBranch.repo_id == repo.id, TrackedBranch.branch == head_ref))).scalar_one_or_none()
            if tracked is not None:
                tracked.next_check_at = datetime.now(timezone.utc)
                if tracked.status == "abandoned":
                    tracked.status = "waiting_for_pr"
    elif event in ("installation", "installation_repositories"):
        installation = data.get("installation") or {}
        inst_id = installation.get("id")
        action = data.get("action")
        if event == "installation" and action == "deleted" and inst_id:
            await db.execute(update(Repo).where(Repo.installation_id == inst_id).values(
                installation_id=None, status="app_missing"))
        elif event == "installation_repositories":
            if action == "added":
                for item in data.get("repositories_added", []):
                    owner, _, name = item.get("full_name", "").partition("/")
                    await db.execute(update(Repo).where(Repo.owner == owner, Repo.name == name).values(
                        installation_id=inst_id, status="active"))
            if action == "removed":
                for item in data.get("repositories_removed", []):
                    owner, _, name = item.get("full_name", "").partition("/")
                    await db.execute(update(Repo).where(Repo.owner == owner, Repo.name == name).values(
                        installation_id=None, status="app_missing"))
    return Response(status_code=204)


@router.get("/github/setup", response_class=HTMLResponse)
async def setup(installation_id: int, setup_action: str | None = None, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    repos = await gh_prs.installation_repositories(get_github(), installation_id)
    names = []
    for item in repos:
        owner, _, name = item["full_name"].partition("/")
        repo = (await db.execute(select(Repo).where(Repo.owner == owner, Repo.name == name))).scalar_one_or_none()
        if repo is not None:
            repo.installation_id = installation_id
            repo.status = "active"
        names.append(item["full_name"])
    items = "".join(f"<li>{html.escape(n)}</li>" for n in names) or "<li>No repositories were selected.</li>"
    page = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Unpack: GitHub App installed</title></head><body style="font-family:system-ui,sans-serif;padding:16px;max-width:640px">
<h1>Unpack is installed</h1><p>Repositories with access:</p><ul>{items}</ul>
<p>Next step: run <code>unpack install</code> in each repository to install the pre-push hook.</p></body></html>"""
    return HTMLResponse(page)
