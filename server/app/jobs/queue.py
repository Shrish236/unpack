"""Postgres job queue: SELECT ... FOR UPDATE SKIP LOCKED (server design §6)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..db import session_scope
from ..models import Job


async def enqueue(
    session: Any,
    job_type: str,
    payload: dict[str, Any],
    *,
    dedupe_key: str | None = None,
    run_after: datetime | None = None,
    max_attempts: int = 4,
) -> int | None:
    values: dict[str, Any] = {
        "type": job_type,
        "payload": payload,
        "status": "queued",
        "attempts": 0,
        "max_attempts": max_attempts,
        "dedupe_key": dedupe_key,
    }
    if run_after is not None:
        values["run_after"] = run_after
    stmt = pg_insert(Job).values(**values)
    if dedupe_key is not None:
        # A job with the same key already queued or running absorbs this one.
        stmt = stmt.on_conflict_do_nothing(index_elements=[Job.dedupe_key])
    result = await session.execute(stmt.returning(Job.id))
    row = result.scalar_one_or_none()
    return int(row) if row is not None else None


async def enqueue_standalone(job_type: str, payload: dict[str, Any], **kwargs: Any) -> int | None:
    async with session_scope() as session:
        return await enqueue(session, job_type, payload, **kwargs)


CLAIM_SQL = text(
    """
    UPDATE jobs SET status = 'running', locked_at = now(), attempts = attempts + 1
    WHERE id = (
        SELECT id FROM jobs
        WHERE status = 'queued' AND run_after <= now()
        ORDER BY run_after
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    RETURNING id, type, payload, attempts, max_attempts
    """
)


async def claim() -> dict[str, Any] | None:
    async with session_scope() as session:
        row = (await session.execute(CLAIM_SQL)).mappings().first()
    return dict(row) if row else None


async def finish(job_id: int) -> None:
    async with session_scope() as session:
        await session.execute(
            text("UPDATE jobs SET status = 'done', dedupe_key = NULL, locked_at = NULL WHERE id = :id"),
            {"id": job_id},
        )


async def retry_later(job_id: int, attempts: int, error: str, delay_seconds: float | None = None) -> None:
    delay = delay_seconds if delay_seconds is not None else 5 * (2 ** attempts)
    run_after = datetime.now(timezone.utc) + timedelta(seconds=delay)
    async with session_scope() as session:
        await session.execute(
            text(
                "UPDATE jobs SET status = 'queued', run_after = :run_after, locked_at = NULL, last_error = :err "
                "WHERE id = :id"
            ),
            {"id": job_id, "run_after": run_after, "err": error[:2000]},
        )


async def fail(job_id: int, error: str) -> None:
    async with session_scope() as session:
        await session.execute(
            text(
                "UPDATE jobs SET status = 'failed', dedupe_key = NULL, locked_at = NULL, last_error = :err "
                "WHERE id = :id"
            ),
            {"id": job_id, "err": error[:2000]},
        )


async def reset_stuck(stuck_seconds: int) -> int:
    async with session_scope() as session:
        result = await session.execute(
            text(
                "UPDATE jobs SET status = 'queued', locked_at = NULL "
                "WHERE status = 'running' AND locked_at < now() - make_interval(secs => :secs)"
            ),
            {"secs": stuck_seconds},
        )
        return result.rowcount or 0
