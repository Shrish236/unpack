"""GitHub OAuth login for viewers (server design §5.4)."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import jwt
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import get_db, session_scope
from ..deps import SESSION_COOKIE, viewer
from ..errors import ApiError
from ..github import prs as gh_prs
from ..models import OAuthState, User, WebSession
from ..security import encrypt_secret, new_session_id
from ..services import get_github, get_oauth_http

router = APIRouter()
STATE_COOKIE = "unpack_oauth_state"
SESSION_DAYS = 14


def _safe_next(value: str | None) -> str:
    if not value or not value.startswith("/a/") or value.startswith("//") or "\\" in value:
        raise ApiError(400, "invalid_next", "next must be a relative /a/ path")
    return value


def _callback_url() -> str:
    return f"{settings.UNPACK_BASE_URL.rstrip('/')}/auth/callback"


@router.get("/auth/login")
async def login(next: str | None = None) -> Response:
    target = _safe_next(next)
    nonce = secrets.token_urlsafe(16)
    async with session_scope() as session:
        session.add(OAuthState(nonce=nonce, expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)))
    state = jwt.encode(
        {"nonce": nonce, "next": target, "exp": datetime.now(timezone.utc) + timedelta(minutes=10)},
        settings.SESSION_SECRET,
        algorithm="HS256",
    )
    query = urlencode({
        "client_id": settings.GITHUB_CLIENT_ID or "",
        "redirect_uri": _callback_url(),
        "state": state,
        "scope": "read:user repo",
    })
    response = RedirectResponse(f"{settings.GITHUB_OAUTH_URL}/authorize?{query}", status_code=302)
    response.set_cookie(STATE_COOKIE, nonce, max_age=600, httponly=True, secure=True,
                        samesite="lax", path="/auth")
    return response


def _login_failed() -> HTMLResponse:
    return HTMLResponse("<!doctype html><meta charset='utf-8'><p>Login failed, try again.</p>", status_code=400)


@router.get("/auth/callback")
async def callback(request: Request, code: str | None = None, state: str | None = None,
                   db: AsyncSession = Depends(get_db)) -> Response:
    if not code or not state:
        return _login_failed()
    try:
        claims = jwt.decode(state, settings.SESSION_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return _login_failed()
    if not secrets.compare_digest(claims.get("nonce", ""), request.cookies.get(STATE_COOKIE, "")):
        return _login_failed()
    # Single use: consuming the row fails if the state was already used or has expired.
    consumed = await db.execute(delete(OAuthState).where(
        OAuthState.nonce == claims["nonce"], OAuthState.expires_at > datetime.now(timezone.utc)))
    if consumed.rowcount != 1:
        return _login_failed()
    target = _safe_next(claims.get("next"))

    async with get_oauth_http() as http:
        token_response = await http.post(
            f"{settings.GITHUB_OAUTH_URL}/access_token",
            json={"client_id": settings.GITHUB_CLIENT_ID, "client_secret": settings.GITHUB_CLIENT_SECRET,
                  "code": code, "redirect_uri": _callback_url()},
            headers={"Accept": "application/json"},
        )
    access_token = token_response.json().get("access_token") if token_response.status_code == 200 else None
    if not access_token:
        return _login_failed()
    try:
        profile = await gh_prs.get_viewer_user(get_github(), access_token)
    except Exception:
        return _login_failed()

    user = (await db.execute(select(User).where(User.github_id == profile["id"]))).scalar_one_or_none()
    if user is None:
        user = User(github_id=profile["id"], login=profile["login"], avatar_url=profile.get("avatar_url"))
        db.add(user)
        await db.flush()
    else:
        user.login = profile["login"]
        user.avatar_url = profile.get("avatar_url")

    session_id = new_session_id()
    db.add(WebSession(id=session_id, user_id=user.id,
                      oauth_token_encrypted=encrypt_secret(access_token),
                      expires_at=datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)))
    await db.flush()

    response = RedirectResponse(target, status_code=302)
    response.set_cookie(SESSION_COOKIE, session_id, max_age=SESSION_DAYS * 86400, httponly=True,
                        secure=True, samesite="lax", path="/")
    response.delete_cookie(STATE_COOKIE, path="/auth")
    return response


@router.post("/auth/logout", status_code=204)
async def logout(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id:
        row = await db.get(WebSession, session_id)
        if row is not None:
            await db.delete(row)
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.get("/api/me")
async def me(auth: tuple[User, str] = Depends(viewer)) -> dict[str, str | None]:
    user, _ = auth
    return {"login": user.login, "avatar_url": user.avatar_url}
