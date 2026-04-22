"""Startup recovery for in-flight searches that were interrupted by a restart.

Background tasks in this bot run as in-process coroutines. If the process is
restarted (Railway redeploy, OOM, crash), any search that was `pending` or
`running` at that moment is effectively lost. On the next startup we:

1. Mark those queries as `failed` in the database so they don't stay orphaned.
2. Try to notify the user (via their Telegram user id, which equals the chat id
   for private chats) so they know to retry instead of waiting forever.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramNotFound
from sqlalchemy import select

from leadgen.db import SearchQuery, session_factory

logger = logging.getLogger(__name__)

STALE_STATUSES = ("pending", "running")
RECOVERY_ERROR_MESSAGE = (
    "Сервис был перезапущен во время выполнения запроса. Запусти поиск ещё раз."
)


async def recover_stale_queries(bot: Bot | None = None) -> int:
    """Mark interrupted queries as failed and optionally notify users.

    Returns the number of queries that were recovered.
    """
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

        user_ids = {q.user_id for q in stale}

    if bot is not None:
        for user_id in user_ids:
            try:
                await bot.send_message(user_id, f"⚠️ {RECOVERY_ERROR_MESSAGE}")
            except (TelegramForbiddenError, TelegramNotFound):
                logger.info("recovery notify: user %s unreachable", user_id)
            except Exception:  # noqa: BLE001
                logger.exception("recovery notify: failed for user %s", user_id)

    return len(stale)
