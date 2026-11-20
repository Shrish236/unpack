"""Worker process: job slots, reconciler loop and heartbeat (server design §6)."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
import traceback

from sqlalchemy import text

from ..config import require_valid_settings, settings
from ..db import session_scope
from . import queue
from .handlers import dispatch, mark_failed_after_retries
from .reconciler import reconcile_once

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s %(message)s")
log = logging.getLogger("unpack.worker")
WORKER_ID = f"{socket.gethostname()}-{os.getpid()}"


async def heartbeat(stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            async with session_scope() as session:
                await session.execute(text(
                    "INSERT INTO worker_heartbeat (worker_id, beat_at) VALUES (:w, now()) "
                    "ON CONFLICT (worker_id) DO UPDATE SET beat_at = now()"
                ), {"w": WORKER_ID})
        except Exception as exc:
            log.warning("heartbeat failed: %s", type(exc).__name__)
        await _sleep(stop, 10)


async def job_slot(stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            job = await queue.claim()
        except Exception as exc:
            log.warning("claim failed: %s", type(exc).__name__)
            await _sleep(stop, 2)
            continue
        if job is None:
            await _sleep(stop, 1)
            continue
        try:
            await dispatch(job["type"], job["payload"])
            await queue.finish(job["id"])
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            retry_after = getattr(exc, "retry_after", None)
            log.warning("job %s (%s) failed: %s", job["id"], job["type"], message[:300])
            log.debug("%s", traceback.format_exc())
            if job["attempts"] >= job["max_attempts"]:
                await queue.fail(job["id"], message)
                try:
                    await mark_failed_after_retries(job["payload"], message) if job["type"] == "analyze_push" else None
                except Exception:
                    log.warning("could not record final failure for job %s", job["id"])
            else:
                await queue.retry_later(job["id"], job["attempts"], message, delay_seconds=retry_after)


async def reconciler_loop(stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            reset = await queue.reset_stuck(settings.JOB_STUCK_SECONDS)
            if reset:
                log.info("reset %s stuck jobs", reset)
            await reconcile_once()
        except Exception as exc:
            log.warning("reconciler tick failed: %s", type(exc).__name__)
        await _sleep(stop, settings.RECONCILE_INTERVAL_SECONDS)


async def _sleep(stop: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


async def run_worker() -> None:
    require_valid_settings()
    log.info("Unpack worker %s starting (%s job slots)", WORKER_ID, settings.WORKER_CONCURRENCY)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass
    tasks = [asyncio.create_task(heartbeat(stop)), asyncio.create_task(reconciler_loop(stop))]
    tasks += [asyncio.create_task(job_slot(stop)) for _ in range(settings.WORKER_CONCURRENCY)]
    await stop.wait()
    log.info("worker shutting down")
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    from ..pipeline.build import shutdown_pool
    from .render import shutdown_browser

    await shutdown_browser()
    shutdown_pool()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
