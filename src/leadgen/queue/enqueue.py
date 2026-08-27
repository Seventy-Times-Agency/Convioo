"""Tiny wrapper around ``arq`` for pushing search jobs.

Keeps the Telegram-side code free of arq imports when Redis isn't
configured — ``is_queue_enabled()`` lets callers choose between
enqueue (for the future web path) and direct ``asyncio.create_task``
(today's bot path).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from leadgen.config import get_settings

logger = logging.getLogger(__name__)


def is_queue_enabled() -> bool:
    return bool(get_settings().redis_url)


async def enqueue_search(
    query_id: uuid.UUID,
    chat_id: int | None,
    user_profile: dict[str, Any] | None,
) -> str | None:
    """Push a search onto the arq queue. Returns the job id or None if
    the queue isn't configured — callers can then fall back to in-
    process execution.
    """
    settings = get_settings()
    if not settings.redis_url:
        return None
    try:
        from arq.connections import RedisSettings, create_pool

        pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        try:
            job = await pool.enqueue_job(
                "run_search_job",
                str(query_id),
                chat_id,
                user_profile,
            )
        finally:
            await pool.close()
        return job.job_id if job is not None else None
    except Exception:  # noqa: BLE001
        logger.exception("enqueue_search: failed to enqueue")
        return None
