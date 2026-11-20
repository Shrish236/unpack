"""Database engine, sessions and declarative base."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings


class Base(DeclarativeBase):
    pass


_engine: AsyncEngine | None = None
_maker: async_sessionmaker[AsyncSession] | None = None


def _normalise_url(url: str) -> str:
    # The design uses postgresql://...; SQLAlchemy's async driver is asyncpg.
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://"):]
    return url


def get_engine() -> AsyncEngine:
    global _engine, _maker
    if _engine is None:
        _engine = create_async_engine(
            _normalise_url(settings.DATABASE_URL), pool_pre_ping=True, pool_size=10, max_overflow=10
        )
        _maker = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    return _engine


def reset_engine(url: str | None = None) -> None:
    """Drop the cached engine (tests point at a different database)."""
    global _engine, _maker
    _engine = None
    _maker = None
    if url is not None:
        settings.DATABASE_URL = url


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    get_engine()
    assert _maker is not None
    async with _maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, committed on success."""
    async with session_scope() as session:
        yield session
