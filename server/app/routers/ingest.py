"""POST /v1/ingest and GET /v1/pushes/{id}: the CLI hook's endpoints (server design §5.1, §5.2)."""

from __future__ import annotations

import gzip
import json
import re
import zlib
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import get_db
from ..deps import ingest_repo
from ..errors import ApiError
from ..jobs.queue import enqueue
from ..models import (
    Analysis, Decision, FunctionReason, PullRequest, Push, Repo, ReviewFinding, Session, SessionSignals, TrackedBranch,
)
from ..schemas.api import IngestPayload
from ..security import new_public_id
from ..pipeline.repos import data_dir

router = APIRouter(prefix="/v1")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
MAX_TEXT_FILE = 1024 * 1024
MAX_DIFF = 5 * 1024 * 1024


def _analysis_url(public_id: str) -> str:
    return f"{settings.UNPACK_BASE_URL.rstrip('/')}/a/{public_id}"


def _decompress(raw: bytes) -> bytes:
    """Gunzip with the uncompressed limit enforced while reading, so a small upload cannot expand past it."""
    if len(raw) > settings.MAX_PAYLOAD_COMPRESSED_BYTES:
        raise ApiError(413, "payload_too_large", "compressed payload is over 25 MB")
    try:
        decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
        out = decompressor.decompress(raw, settings.MAX_PAYLOAD_UNCOMPRESSED_BYTES + 1)
    except zlib.error as exc:
        raise ApiError(415, "unsupported_encoding", "body is not valid gzip") from exc
    if len(out) > settings.MAX_PAYLOAD_UNCOMPRESSED_BYTES:
        raise ApiError(413, "payload_too_large", "uncompressed payload is over 150 MB")
    return out


def _validate(payload: dict[str, Any]) -> IngestPayload:
    version = payload.get("schema_version")
    if version != 1:
        raise ApiError(422, "unsupported_schema_version", "unsupported schema_version",
                       {"supported": [1]})
    try:
        data = IngestPayload.model_validate(payload)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first.get("loc", ()))
        raise ApiError(400, "invalid_payload", f"{where}: {first.get('msg')}") from exc
    if not data.branch or data.branch.startswith("refs/"):
        raise ApiError(400, "invalid_payload", "branch must be non-empty and must not start with refs/")
    for label, value in (("base_sha", data.base_sha), ("head_sha", data.head_sha)):
        if not SHA_RE.match(value):
            raise ApiError(400, "invalid_payload", f"{label} must be 40 lowercase hex characters")
    if len(data.commits) > 500:
        raise ApiError(400, "invalid_payload", "at most 500 commits")
    for commit in data.commits:
        if not SHA_RE.match(commit.sha):
            raise ApiError(400, "invalid_payload", "commit sha must be 40 lowercase hex characters")
    if len(data.diff.encode("utf-8")) > MAX_DIFF:
        raise ApiError(413, "payload_too_large", "diff is over 5 MB")
    for f in data.changed_files:
        if f.status == "R" and not f.old_path:
            raise ApiError(400, "invalid_payload", f"{f.path}: renamed file needs old_path")
        for content in (f.base_content, f.head_content):
            if content is not None and len(content.encode("utf-8")) > MAX_TEXT_FILE:
                raise ApiError(400, "invalid_payload", f"{f.path}: file content is over 1 MB; send null and truncated")
    return data


def _push_response(push: Push, analysis: Analysis, tracking_status: str, branch: str, deduplicated: bool) -> dict[str, Any]:
    return {
        "push_id": push.id,
        "analysis": {"public_id": analysis.public_id, "status": analysis.status,
                     "url": _analysis_url(analysis.public_id)},
        "tracking": {"branch": branch, "status": tracking_status},
        "deduplicated": deduplicated,
    }


async def _reanalyse_with_session(
    db: AsyncSession, repo: Repo, push: Push, analysis: Analysis, data: IngestPayload, payload_bytes: bytes,
) -> None:
    """Replace a session-less analysis with one that has the session. The public id and URL stay the same."""
    push_dir = data_dir() / "payloads" / str(repo.id)
    push_dir.mkdir(parents=True, exist_ok=True)
    path = push_dir / f"{data.head_sha}-{new_public_id()}.json.gz"
    path.write_bytes(gzip.compress(payload_bytes))
    push.payload_path = str(path)
    push.has_session = True
    push.session_agent = data.session.agent
    push.redaction_counts = data.redactions
    for model, col in ((FunctionReason, FunctionReason.analysis_id), (ReviewFinding, ReviewFinding.analysis_id),
                       (Decision, Decision.analysis_id), (SessionSignals, SessionSignals.analysis_id)):
        await db.execute(delete(model).where(col == analysis.id))
    await db.execute(delete(Session).where(Session.push_id == push.id))
    analysis.status = "queued"
    analysis.error_code = None
    analysis.error_message = None
    analysis.finished_at = None
    await db.flush()
    await enqueue(db, "analyze_push", {"analysis_id": analysis.id}, dedupe_key=f"analyze:{analysis.id}")


@router.post("/ingest")
async def ingest(request: Request, repo: Repo = Depends(ingest_repo), db: AsyncSession = Depends(get_db)):
    content_type = request.headers.get("content-type", "")
    if request.headers.get("content-encoding", "").lower() != "gzip":
        raise ApiError(415, "unsupported_encoding", "Content-Encoding must be gzip")
    if not content_type.startswith("application/json"):
        raise ApiError(415, "unsupported_encoding", "Content-Type must be application/json")

    raw = await request.body()
    try:
        payload_bytes = _decompress(raw)
        obj = json.loads(payload_bytes.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ApiError(400, "invalid_payload", "body is not valid JSON") from exc
    if not isinstance(obj, dict):
        raise ApiError(400, "invalid_payload", "body must be a JSON object")
    data = _validate(obj)

    if data.repo.owner.lower() != repo.owner.lower() or data.repo.name.lower() != repo.name.lower():
        raise ApiError(403, "repo_mismatch", "the payload repository is not the token's repository")
    if repo.status != "active":
        details = {}
        if repo.status == "app_missing":
            details["install_url"] = f"https://github.com/apps/{settings.GITHUB_APP_SLUG}/installations/new"
        raise ApiError(409, "repo_disabled", "repository is disabled or the GitHub App is not installed", details)

    since = datetime.now(timezone.utc) - timedelta(seconds=60)
    recent = (await db.execute(select(func.count()).select_from(Push).where(
        Push.repo_id == repo.id, Push.received_at >= since))).scalar_one()
    if recent >= settings.PUSHES_PER_MINUTE_PER_REPO:
        raise ApiError(429, "rate_limited", "too many pushes; slow down", headers={"Retry-After": "60"})

    existing = (await db.execute(select(Push).where(
        Push.repo_id == repo.id, Push.head_sha == data.head_sha))).scalar_one_or_none()
    if existing is not None:
        analysis = (await db.execute(select(Analysis).where(Analysis.push_id == existing.id))).scalar_one()
        tracked = (await db.execute(select(TrackedBranch).where(
            TrackedBranch.repo_id == repo.id, TrackedBranch.branch == existing.branch))).scalar_one_or_none()
        status = tracked.status if tracked else "untracked"
        if data.session is not None and not existing.has_session and analysis.status in ("done", "failed"):
            # The first push of this head had no agent session (it was found late, or the hook ran before the agent
            # finished). Analysing again with the session is worth more than keeping the session-less result.
            await _reanalyse_with_session(db, repo, existing, analysis, data, payload_bytes)
            return JSONResponse(_push_response(existing, analysis, status, existing.branch, False), status_code=202)
        return JSONResponse(_push_response(existing, analysis, status, existing.branch, True), status_code=200)

    push_dir = data_dir() / "payloads" / str(repo.id)
    push_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"{data.head_sha}-{new_public_id()}.json.gz"
    payload_path = push_dir / file_name
    payload_path.write_bytes(gzip.compress(payload_bytes))

    session_payload = data.session
    push = Push(
        repo_id=repo.id,
        branch=data.branch,
        base_sha=data.base_sha,
        head_sha=data.head_sha,
        commits=[c.model_dump() for c in data.commits],
        payload_path=str(payload_path),
        has_session=session_payload is not None,
        session_agent=session_payload.agent if session_payload else None,
        redaction_counts=data.redactions,
        cli_version=data.client.cli_version,
    )
    db.add(push)
    try:
        async with db.begin_nested():
            await db.flush()
    except Exception:
        # Lost a race with the same head_sha: answer as a duplicate.
        existing = (await db.execute(select(Push).where(
            Push.repo_id == repo.id, Push.head_sha == data.head_sha))).scalar_one()
        analysis = (await db.execute(select(Analysis).where(Analysis.push_id == existing.id))).scalar_one()
        return JSONResponse(_push_response(existing, analysis, "untracked", existing.branch, True), status_code=200)

    analysis = Analysis(push_id=push.id, public_id=new_public_id(), status="queued")
    db.add(analysis)
    await db.flush()

    tracking_status = "untracked"
    if data.branch != repo.default_branch:
        tracked = (await db.execute(select(TrackedBranch).where(
            TrackedBranch.repo_id == repo.id, TrackedBranch.branch == data.branch))).scalar_one_or_none()
        if tracked is None:
            tracked = TrackedBranch(repo_id=repo.id, branch=data.branch)
            db.add(tracked)
        if tracked.status != "linked":
            tracked.status = "waiting_for_pr"
        tracked.latest_push_id = push.id
        tracked.latest_head_sha = data.head_sha
        tracked.needs_publish = True
        tracking_status = tracked.status

    await enqueue(db, "analyze_push", {"analysis_id": analysis.id}, dedupe_key=f"analyze:{analysis.id}")
    return JSONResponse(_push_response(push, analysis, tracking_status, data.branch, False), status_code=202)


@router.get("/pushes/{push_id}")
async def get_push(push_id: int, repo: Repo = Depends(ingest_repo), db: AsyncSession = Depends(get_db)):
    push = await db.get(Push, push_id)
    if push is None or push.repo_id != repo.id:
        raise ApiError(404, "not_found", "no such push")
    analysis = (await db.execute(select(Analysis).where(Analysis.push_id == push.id))).scalar_one()
    tracked = (await db.execute(select(TrackedBranch).where(
        TrackedBranch.repo_id == repo.id, TrackedBranch.branch == push.branch))).scalar_one_or_none()
    prs = (await db.execute(select(PullRequest).where(
        PullRequest.repo_id == repo.id, PullRequest.head_ref == push.branch))).scalars().all()
    return {
        "push_id": push.id,
        "branch": push.branch,
        "head_sha": push.head_sha,
        "received_at": push.received_at.isoformat() if push.received_at else None,
        "analysis": {"public_id": analysis.public_id, "status": analysis.status,
                     "error": analysis.error_code, "url": _analysis_url(analysis.public_id)},
        "tracking": {"status": tracked.status if tracked else "untracked",
                     },
        "pull_requests": [
            {"number": pr.number, "url": pr.html_url, "comment_url": pr.comment_url,
             "published_analysis_is_this_push": pr.last_published_analysis_id == analysis.id}
            for pr in prs if pr.state == "open"
        ],
    }
