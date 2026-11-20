"""Comment images, the internal render route and the static viewer app (server design §5.5, §5.6, §9)."""

from __future__ import annotations

import ipaddress
import re
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from ..errors import ApiError
from ..jobs.render import images_dir
from ..security import verify_render_token

router = APIRouter()
IMAGE_RE = re.compile(r"^[0-9a-f]{32}\.png$")
WEB_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"


def web_index() -> Path | None:
    index = WEB_DIST / "index.html"
    return index if index.exists() else None


@router.get("/img/{file_name}")
async def image(file_name: str) -> Response:
    if not IMAGE_RE.match(file_name):
        raise ApiError(404, "not_found", "no such image")
    path = images_dir() / file_name
    if not path.exists():
        raise ApiError(404, "not_found", "no such image")
    return FileResponse(path, media_type="image/png",
                        headers={"Cache-Control": "public, max-age=31536000, immutable"})


def _internal(request: Request) -> bool:
    host = request.client.host if request.client else ""
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return host == "localhost"
    return addr.is_loopback or (addr.is_private and not addr.is_global)


@router.get("/render/{public_id}")
async def render_page(public_id: str, request: Request, render_token: str | None = None) -> Response:
    if not _internal(request):
        raise ApiError(403, "forbidden", "render is internal only")
    if not verify_render_token(public_id, render_token):
        raise ApiError(403, "forbidden", "invalid or expired render token")
    index = web_index()
    if index is None:
        return JSONResponse({"error": {"code": "unavailable", "message": "web UI is not built"}}, status_code=503)
    return FileResponse(index, media_type="text/html")


@router.get("/a/{public_id}")
async def app_page(public_id: str) -> Response:
    index = web_index()
    if index is None:
        return JSONResponse({"error": {"code": "unavailable", "message": "web UI is not built"}}, status_code=503)
    return FileResponse(index, media_type="text/html")


@router.get("/favicon.ico")
async def favicon() -> Response:
    # No icon yet. A 204 keeps browsers from logging a 404, which would fail the comment image render.
    return Response(status_code=204)
