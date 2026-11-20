"""Authentication dependencies: ingest token, admin token, viewer session and repo access (server design §5.4, §11)."""

from __future__ import annotations

import hmac
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .db import get_db
from .errors import ApiError
from .github import prs as gh_prs
from .github.service import GitHubError
from .models import AccessCache, Repo, User, WebSession
from .security import decrypt_secret, hash_token
from .services import get_github

SESSION_COOKIE = "unpack_session"


def bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return None


async def ingest_repo(request: Request, db: AsyncSession = Depends(get_db)) -> Repo:
    token = bearer(request)
    if not token:
        raise ApiError(401, "invalid_token", "missing ingest token")
    repo = (await db.execute(select(Repo).where(Repo.ingest_token_hash == hash_token(token)))).scalar_one_or_none()
    if repo is None:
        raise ApiError(401, "invalid_token", "unknown ingest token")
    request.state.repo_id = repo.id
    return repo


def require_admin(request: Request) -> None:
    token = bearer(request)
    if not token or not hmac.compare_digest(token, settings.ADMIN_TOKEN):
        raise ApiError(401, "unauthorized", "admin token required")


async def viewer(request: Request, db: AsyncSession = Depends(get_db)) -> tuple[User, str]:
    """The logged-in user and their GitHub token. 401 not_logged_in otherwise."""
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id:
        raise ApiError(401, "not_logged_in", "log in with GitHub")
    row = await db.get(WebSession, session_id)
    if row is None or row.expires_at <= datetime.now(timezone.utc):
        if row is not None:
            await db.delete(row)
        raise ApiError(401, "not_logged_in", "log in with GitHub")
    user = await db.get(User, row.user_id)
    return user, decrypt_secret(row.oauth_token_encrypted)


async def require_repo_access(db: AsyncSession, user: User, token: str, repo: Repo) -> None:
    """Design §5.5: cached for 10 minutes, otherwise checked against GitHub with the viewer's token."""
    cached = await db.get(AccessCache, (user.id, repo.id))
    fresh = cached is not None and cached.checked_at is not None and (
        datetime.now(timezone.utc) - cached.checked_at.astimezone(timezone.utc)
    ) < timedelta(seconds=settings.ACCESS_CACHE_SECONDS)
    if fresh:
        if cached.allowed:
            return
        raise ApiError(403, "no_repo_access", "you don't have access to this repository")
    try:
        status = await gh_prs.get_viewer_repo(get_github(), token, repo.owner, repo.name)
    except GitHubError as exc:
        raise ApiError(503, "unavailable", f"GitHub is unavailable: {exc.status}") from exc
    if status == 401:
        session = await db.execute(select(WebSession).where(WebSession.user_id == user.id))
        for row in session.scalars().all():
            await db.delete(row)
        await db.commit()  # keep the revocation even though the request fails
        raise ApiError(401, "not_logged_in", "GitHub login has expired")
    allowed = status == 200
    if cached is None:
        db.add(AccessCache(user_id=user.id, repo_id=repo.id, allowed=allowed, checked_at=datetime.now(timezone.utc)))
    else:
        cached.allowed = allowed
        cached.checked_at = datetime.now(timezone.utc)
    await db.commit()  # keep the cache entry even though the request may fail
    if not allowed:
        raise ApiError(403, "no_repo_access", "you don't have access to this repository")
