"""GitHub App post-install setup page (server design §5.3). The webhook endpoint is gone: the poller
keeps installations in step (reconciler.sync_installations)."""

from __future__ import annotations

import html

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..errors import ApiError
from ..github.service import GitHubError
from ..github import prs as gh_prs
from ..models import Repo
from ..services import get_github

router = APIRouter()


@router.get("/github/setup", response_class=HTMLResponse)
async def setup(installation_id: int, setup_action: str | None = None, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    try:
        repos = await gh_prs.installation_repositories(get_github(), installation_id)
    except GitHubError as exc:
        raise ApiError(503, "unavailable", f"could not read the GitHub App installation ({exc.status})") from exc
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
