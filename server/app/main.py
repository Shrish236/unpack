"""FastAPI application for Unpack: routers, security headers, errors and health checks."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .config import require_valid_settings
from .db import get_engine, session_scope
from .errors import ApiError, api_error_handler, error_body
from .routers import admin, auth, github_setup, images, ingest, live

CSP = (
    "default-src 'self'; "
    "img-src 'self' https://avatars.githubusercontent.com data:; "
    "style-src 'self' 'unsafe-inline'; "
    "worker-src 'self' blob:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    require_valid_settings()
    get_engine()
    yield
    await get_engine().dispose()


app = FastAPI(
    title="Unpack API",
    version="0.2.0",
    description="Turns AI-written code changes into an explained, explorable graph",
    lifespan=lifespan,
)
app.add_exception_handler(ApiError, api_error_handler)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    first = exc.errors()[0]
    where = ".".join(str(p) for p in first.get("loc", ()) if p not in ("query", "body", "path"))
    return JSONResponse(status_code=400, content=error_body("invalid_payload", f"{where}: {first.get('msg')}"))


@app.middleware("http")
async def headers(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = CSP
    return response


app.include_router(ingest.router)
app.include_router(github_setup.router)
app.include_router(auth.router)
app.include_router(live.router)
app.include_router(admin.router)
app.include_router(images.router)


@app.get("/healthz")
async def healthz() -> dict[str, bool]:
    return {"ok": True}


@app.get("/readyz")
async def readyz() -> JSONResponse:
    result: dict[str, object] = {}
    failing = False
    try:
        async with session_scope() as session:
            await session.execute(text("SELECT 1"))
        result["postgres"] = "ok"
    except Exception:
        result["postgres"] = "failing"
        failing = True
    try:
        async with session_scope() as session:
            beat = (await session.execute(text(
                "SELECT max(beat_at) FROM worker_heartbeat"))).scalar_one_or_none()
        age = (datetime.now(timezone.utc) - beat).total_seconds() if beat else None
        result["worker_heartbeat_age_s"] = int(age) if age is not None else None
        result["worker"] = "ok" if age is not None and age < 60 else "failing"
        if result["worker"] == "failing":
            failing = True
    except Exception:
        result["worker"] = "failing"
        failing = True
    return JSONResponse(result, status_code=503 if failing else 200)


STATIC_DIR = Path(__file__).resolve().parents[2] / "web" / "dist" / "assets"
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR)), name="assets")
