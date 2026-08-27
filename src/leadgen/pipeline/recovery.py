"""Startup recovery for in-flight searches that were interrupted by a restart.

Background tasks run as in-process coroutines (or as arq jobs). If the
process is restarted (Railway redeploy, OOM, crash), any search that
was `pending` or `running` at that moment is effectively lost. On the
next startup we mark those queries as `failed` so they don't stay
orphaned and the user sees an error in the UI instead of an infinite
spinner.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from leadgen.db import SearchQuery, session_factory

logger = logging.getLogger(__name__)

STALE_STATUSES = ("pending", "running")
RECOVERY_ERROR_MESSAGE = (
    "The service was restarted while this search was running. Run it again."
)


async def recover_stale_queries() -> int:
    """Mark interrupted queries as failed. Returns the count recovered."""
    now = datetime.now(timezone.utc)

    async with session_factory() as session:
        result = await session.execute(
            select(SearchQuery).where(SearchQuery.status.in_(STALE_STATUSES))
        )
        stale = list(result.scalars().all())

        if not stale:
            return 0

        for query in stale:
            query.status = "failed"
            query.error = RECOVERY_ERROR_MESSAGE
            query.finished_at = now

        await session.commit()
        logger.warning("Recovered %d stale queries on startup", len(stale))

    return len(stale)
