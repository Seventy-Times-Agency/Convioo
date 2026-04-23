from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from leadgen.config import get_settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            get_settings().sqlalchemy_url,
            echo=False,
            pool_pre_ping=True,
        )
    return _engine


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            _get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _session_factory


def session_factory() -> AsyncSession:  # type: ignore[return]
    """Open a new async session from the lazily-initialised factory.

    Behaves like calling the underlying ``async_sessionmaker`` directly so
    existing ``async with session_factory() as session:`` call-sites keep
    working unchanged.
    """
    return _get_session_factory()()


async def init_db() -> None:
    """Validate database connectivity.

    Schema management is handled by Alembic migrations.
    """
    async with _get_engine().connect() as conn:
        await conn.execute(text("SELECT 1"))


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    async with _get_session_factory()() as session:
        yield session
