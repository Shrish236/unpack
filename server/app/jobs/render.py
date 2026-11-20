"""Comment image: the graph page in headless Chromium (server design §9).

The page sets body[data-ready]="true" when drawing is complete, or data-error on failure.
Rendering fails on timeout, data-error, console errors, failed requests, oversized files and
blank images. The comment is then published without an image.
"""

from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path
from typing import Any

from ..config import settings
from ..security import render_token

MAX_BYTES = 2 * 1024 * 1024
MIN_STDDEV = 2.0


class RenderFailed(Exception):
    pass


def images_dir() -> Path:
    path = Path(settings.DATA_DIR) / "images"
    path.mkdir(parents=True, exist_ok=True)
    return path


def check_image(data: bytes) -> None:
    """Size and not-blank checks. Raises RenderFailed."""
    if len(data) > MAX_BYTES:
        raise RenderFailed("image is larger than 2 MB")
    from PIL import Image, ImageStat

    with Image.open(BytesIO(data)) as img:
        grey = img.convert("L")
        stddev = ImageStat.Stat(grey).stddev[0]
    if stddev < MIN_STDDEV:
        raise RenderFailed("image is blank")


async def render_png(public_id: str, file_name: str) -> Path:
    """Renders /render/{public_id} to images/{file_name}. Returns the path."""
    from playwright.async_api import async_playwright

    token = render_token(public_id)
    url = f"{settings.INTERNAL_API_URL.rstrip('/')}/render/{public_id}?static=1&render_token={token}"
    errors: list[str] = []
    async with async_playwright() as pw:
        launch_args: dict[str, Any] = {"args": ["--no-sandbox"]}
        if settings.RENDER_CHROMIUM_PATH:
            launch_args["executable_path"] = settings.RENDER_CHROMIUM_PATH
        browser = await pw.chromium.launch(**launch_args)
        try:
            page = await browser.new_page(
                viewport={"width": 1200, "height": 700},
                device_scale_factor=2,
                color_scheme="light",
            )
            page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
            page.on("requestfailed", lambda req: errors.append(f"request failed: {req.url}"))
            response = await page.goto(url, wait_until="load", timeout=20000)
            if response is None or response.status != 200:
                raise RenderFailed(f"render page returned {response.status if response else 'no response'}")
            try:
                await page.wait_for_function(
                    "document.body && (document.body.dataset.ready === 'true' || document.body.dataset.error)",
                    timeout=20000,
                )
            except Exception as exc:
                raise RenderFailed("render timed out") from exc
            error_text = await page.evaluate("document.body.dataset.error || ''")
            if error_text:
                raise RenderFailed(f"page reported an error: {error_text[:200]}")
            if errors:
                raise RenderFailed("the page logged errors")
            data = await page.screenshot(type="png", full_page=False)
        finally:
            await browser.close()
    check_image(data)
    path = images_dir() / f"{file_name}.png"
    path.write_bytes(data)
    return path


async def render_with_retry(public_id: str, file_name: str) -> Path:
    last: Exception | None = None
    for _ in range(2):
        try:
            return await render_png(public_id, file_name)
        except RenderFailed as exc:
            last = exc
        except Exception as exc:  # browser missing, navigation error: retry once, then fail
            last = exc
        await asyncio.sleep(1)
    raise RenderFailed(str(last) if last else "render failed")


def describe(payload: Any) -> str:
    return str(payload)[:200]
