"""Lightweight liveness probes for the /health endpoint.

Each probe is best-effort: an exception or a missing dependency returns
``None`` so the surrounding handler can decide whether to surface it
as 'unknown' vs 'down'. The probes never raise.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from leadgen.config import get_settings

logger = logging.getLogger(__name__)

# Cap any one probe so a slow Redis / DNS hang can't extend the
# /health response past a couple of seconds. Healthcheckers (Railway,
# uptime monitors) typically time out at 5-10s.
_PROBE_TIMEOUT = 2.0


async def probe_db() -> bool:
    """SELECT 1 against the configured Postgres / SQLite engine."""
    from sqlalchemy import text as sa_text

    from leadgen.db.session import _get_engine

    try:
        engine = _get_engine()
        async with engine.connect() as conn:
            result = await asyncio.wait_for(
                conn.execute(sa_text("SELECT 1")), timeout=_PROBE_TIMEOUT
            )
            return result.scalar() == 1
    except Exception:  # noqa: BLE001
        logger.exception("health: db probe failed")
        return False


async def probe_redis_and_queue() -> tuple[bool | None, int | None]:
    """Ping Redis and read the arq queue depth.

    Returns ``(redis_ok, queue_depth)``. When ``REDIS_URL`` is empty
    both are ``None`` — that means "not configured", which is a valid
    deployment shape (the bot runs without arq today).
    """
    settings = get_settings()
    if not settings.redis_url:
        return None, None

    try:
        from arq.connections import RedisSettings, create_pool

        pool = await asyncio.wait_for(
            create_pool(RedisSettings.from_dsn(settings.redis_url)),
            timeout=_PROBE_TIMEOUT,
        )
    except Exception:  # noqa: BLE001
        logger.warning("health: redis pool create failed", exc_info=True)
        return False, None

    try:
        ping_ok = await asyncio.wait_for(pool.ping(), timeout=_PROBE_TIMEOUT)
        if not ping_ok:
            return False, None
        # Default arq queue name is "arq:queue". Reading the length is
        # O(1) on Redis. Failure to read shouldn't fail the redis
        # probe — Redis is up, we just couldn't introspect the queue.
        depth: int | None = None
        try:
            depth = await asyncio.wait_for(
                pool.zcard("arq:queue"), timeout=_PROBE_TIMEOUT
            )
        except Exception:  # noqa: BLE001
            logger.debug("health: failed to read arq queue depth", exc_info=True)
        return True, depth
    except Exception:  # noqa: BLE001
        logger.warning("health: redis ping failed", exc_info=True)
        return False, None
    finally:
        with contextlib.suppress(Exception):
            await pool.close()


async def probes_for_health() -> dict[str, Any]:
    """Run every probe in parallel. Used by the /health handler."""
    db_task = asyncio.create_task(probe_db())
    redis_task = asyncio.create_task(probe_redis_and_queue())
    db_ok = await db_task
    redis_ok, queue_depth = await redis_task
    return {
        "db": db_ok,
        "redis": redis_ok,
        "queue_depth": queue_depth,
    }
