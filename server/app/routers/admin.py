"""Operations endpoints behind the admin token (server design §5.7)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import get_db
from ..deps import require_admin
from ..errors import ApiError
from ..github import prs as gh_prs
from ..github.service import GitHubError
from ..jobs.queue import enqueue
from ..models import Analysis, Job, Push, Repo, TrackedBranch
from ..security import hash_token, new_ingest_token
from ..services import get_github

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


class RepoIn(BaseModel):
    owner: str = Field(min_length=1)
    name: str = Field(min_length=1)
    default_branch: str = "main"


class RebuildIn(BaseModel):
    sha: str | None = None


@router.post("/repos", status_code=201)
async def create_repo(body: RepoIn, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    if not settings.GITHUB_APP_ID:
        raise ApiError(503, "app_not_configured", "the GitHub App is not configured")
    existing = (await db.execute(select(Repo).where(
        Repo.owner == body.owner, Repo.name == body.name))).scalar_one_or_none()
    if existing is not None:
        raise ApiError(409, "repo_exists", "repository already exists", {"repo_id": existing.id})
    try:
        installation_id = await gh_prs.installation_id_for_repo(get_github(), body.owner, body.name)
    except GitHubError as exc:
        raise ApiError(503, "unavailable", f"GitHub is unavailable: {exc.status}") from exc
    if installation_id is None:
        raise ApiError(409, "app_not_installed", "the GitHub App is not installed on this repository",
                       {"install_url": f"https://github.com/apps/{settings.GITHUB_APP_SLUG}/installations/new"})
    token = new_ingest_token()
    repo = Repo(owner=body.owner, name=body.name, remote_url=f"https://github.com/{body.owner}/{body.name}.git",
                default_branch=body.default_branch, installation_id=installation_id,
                ingest_token_hash=hash_token(token), status="active")
    db.add(repo)
    await db.flush()
    return {"repo_id": repo.id, "ingest_token": token, "installation_id": installation_id}


@router.post("/repos/{repo_id}/rotate-token")
async def rotate_token(repo_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    repo = await db.get(Repo, repo_id)
    if repo is None:
        raise ApiError(404, "not_found", "no such repository")
    token = new_ingest_token()
    repo.ingest_token_hash = hash_token(token)
    return {"ingest_token": token}


@router.post("/repos/{repo_id}/graph/rebuild")
async def rebuild_graph(repo_id: int, body: RebuildIn | None = None, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    repo = await db.get(Repo, repo_id)
    if repo is None:
        raise ApiError(404, "not_found", "no such repository")
    sha = body.sha if body and body.sha else None
    if sha is None:
        push = (await db.execute(select(Push).where(Push.repo_id == repo.id)
                                 .order_by(Push.id.desc()).limit(1))).scalar_one_or_none()
        if push is None:
            raise ApiError(400, "invalid_payload", "no push yet; pass sha")
        sha = push.head_sha
    job_id = await enqueue(db, "build_graph", {"repo_id": repo.id, "sha": sha}, dedupe_key=f"graph:{repo.id}:{sha}")
    return JSONResponse({"job_id": job_id}, status_code=202)


@router.get("/jobs")
async def list_jobs(status: str | None = None, type: str | None = None,
                    limit: int = Query(50, ge=1, le=500), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    query = select(Job).order_by(Job.id.desc()).limit(limit)
    if status:
        query = query.where(Job.status == status)
    if type:
        query = query.where(Job.type == type)
    rows = (await db.execute(query)).scalars().all()
    return {"jobs": [
        {"id": j.id, "type": j.type, "status": j.status, "attempts": j.attempts,
         "last_error": j.last_error, "created_at": j.created_at.isoformat() if j.created_at else None}
        for j in rows
    ]}


@router.post("/analyses/{public_id}/retry", status_code=202)
async def retry_analysis(public_id: str, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    analysis = (await db.execute(select(Analysis).where(Analysis.public_id == public_id))).scalar_one_or_none()
    if analysis is None:
        raise ApiError(404, "not_found", "no such analysis")
    if analysis.status != "failed":
        raise ApiError(409, "not_failed", "only failed analyses can be retried")
    analysis.status = "queued"
    analysis.error_code = None
    analysis.error_message = None
    await enqueue(db, "analyze_push", {"analysis_id": analysis.id}, dedupe_key=f"analyze:{analysis.id}")
    return JSONResponse({"public_id": public_id, "status": "queued"}, status_code=202)


@router.get("/tracked-branches")
async def tracked_branches(status: str | None = None, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    query = select(TrackedBranch, Repo).join(Repo, Repo.id == TrackedBranch.repo_id)
    if status:
        query = query.where(TrackedBranch.status == status)
    rows = (await db.execute(query.limit(200))).all()
    return {"branches": [
        {"id": t.id, "repo": f"{r.owner}/{r.name}", "branch": t.branch, "status": t.status,
         "latest_head_sha": t.latest_head_sha, "needs_publish": t.needs_publish}
        for t, r in rows
    ]}
