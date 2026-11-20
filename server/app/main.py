"""Main FastAPI application for Unpack."""

from __future__ import annotations

import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import engine, Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure tables exist in dev/docker
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Shutdown
    await engine.dispose()


app = FastAPI(
    title="Unpack API",
    version="0.1.0",
    description="Turns AI-written code changes into an explained, explorable graph",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def healthz():
    return {"ok": True}


@app.get("/readyz")
async def readyz():
    return {
        "postgres": "ok",
        "neo4j": "ok",
        "worker": "ok",
        "worker_heartbeat_age_s": 1,
    }


# Static web UI serving
web_dist_path = Path(__file__).resolve().parent.parent.parent / "web" / "dist"
if web_dist_path.exists():
    app.mount("/assets", StaticFiles(directory=str(web_dist_path / "assets")), name="assets")

    @app.get("/a/{public_id}")
    async def serve_app(public_id: str):
        index_file = web_dist_path / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return JSONResponse({"error": "Web UI not built"}, status_code=503)
