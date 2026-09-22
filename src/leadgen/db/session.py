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
        url = get_settings().sqlalchemy_url
        if url.startswith("sqlite"):
            # Zero-config first run: plain SQLite engine — the
            # asyncpg pool knobs and server_settings below don't
            # apply to aiosqlite and would crash the connect.
            _engine = create_async_engine(url, echo=False)
        else:
            _engine = create_async_engine(
                url,
                echo=False,
                pool_pre_ping=True,
                pool_size=20,
                max_overflow=40,
                pool_recycle=1800,
                pool_timeout=30,
                connect_args={
                    "server_settings": {"jit": "off"},
                    "command_timeout": 60,
                },
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

    On Postgres, schema management is handled by Alembic migrations.
    On SQLite (zero-config first run, no DATABASE_URL) the alembic
    chain doesn't apply — the schema is created straight from the
    models here, idempotently, before anything queries it.
    """
    engine = _get_engine()
    if str(engine.url).startswith("sqlite"):
        from leadgen.db.models import Base

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def dispose_engine() -> None:
    """Drop the cached engine + session factory.

    Required when the engine was created in a short-lived asyncio loop
    (e.g. ``asyncio.run(_startup())`` during boot) and the long-lived
    server loop will need fresh connections. Without this, asyncpg
    raises 'Event loop is closed' / 'another operation is in progress'
    on every subsequent query.
    """
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
    _session_factory = None


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    async with _get_session_factory()() as session:
        yield session
