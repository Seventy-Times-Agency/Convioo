from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.fsm.storage.memory import MemoryStorage

from leadgen.bot.handlers import router
from leadgen.bot.middlewares import DbSessionMiddleware
from leadgen.config import get_settings
from leadgen.db.session import init_db, session_factory
from leadgen.pipeline import recover_stale_queries

logger = logging.getLogger(__name__)


async def run() -> None:
    settings = get_settings()

    # Root logging is already set up in __main__.py; just tune the level.
    logging.getLogger().setLevel(settings.log_level)

    logger.info("=== run() entered ===")

    logger.info("Checking database connectivity...")
    try:
        await init_db()
        logger.info("✅ Database reachable")
    except Exception:
        logger.exception("❌ Database init failed — aborting startup")
        raise

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    try:
        me = await bot.get_me()
        logger.info(
            "✅ Bot identity: @%s (id=%s, name=%r)",
            me.username,
            me.id,
            me.full_name,
        )
    except TelegramUnauthorizedError:
        logger.critical(
            "❌ BOT_TOKEN is invalid — Telegram rejected get_me(). "
            "Check BOT_TOKEN in Railway Variables."
        )
        raise
    except Exception:
        logger.exception("❌ get_me() failed — aborting")
        raise

    # Explicit webhook check so the log tells us the story without any
    # out-of-band diagnostics.
    try:
        wh = await bot.get_webhook_info()
        logger.info(
            "Webhook before cleanup: url=%r, pending=%d, last_error=%r",
            wh.url or "",
            wh.pending_update_count,
            wh.last_error_message,
        )
        if wh.url:
            logger.warning(
                "⚠️ A webhook was set to %r — deleting so polling works", wh.url
            )
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("✅ delete_webhook done (pending updates dropped)")
    except Exception:
        logger.exception("Webhook cleanup failed; polling may not receive updates")

    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(DbSessionMiddleware(session_factory))
    dp.include_router(router)

    try:
        recovered = await recover_stale_queries(bot)
        if recovered:
            logger.warning(
                "Startup recovery: %d stale queries marked as failed", recovered
            )
        else:
            logger.info("Startup recovery: no stale queries")
    except Exception:
        logger.exception("Startup recovery failed; continuing anyway")

    logger.info("🚀 Entering polling loop — bot is now live")
    try:
        await dp.start_polling(bot)
    finally:
        logger.info("🛑 Polling stopped, closing bot session")
        await bot.session.close()
