"""Alembic environment: async engine from the server settings, metadata from the ORM models."""

from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from server.app import models  # noqa: F401  (registers the tables)
from server.app.config import settings
from server.app.db import Base, _normalise_url

config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=_normalise_url(settings.DATABASE_URL), target_metadata=target_metadata,
                      literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def _do_run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(_normalise_url(settings.DATABASE_URL))
    async with engine.connect() as connection:
        await connection.run_sync(_do_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
