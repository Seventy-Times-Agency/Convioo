from __future__ import annotations

import asyncio
import contextlib
import logging
import os

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent

from leadgen.adapters.web_api import create_app
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
    # DbSession + user injection must fire for BOTH message and callback
    # events; otherwise inline-button handlers see `user=None` / `session=None`,
    # blow up on the first attribute access, and — because `callback.answer()`
    # is never reached — the user sees a permanent spinner on every button tap.
    db_mw = DbSessionMiddleware(session_factory)
    dp.message.middleware(db_mw)
    dp.callback_query.middleware(db_mw)
    dp.include_router(router)

    # Global safety net: any unhandled exception inside a callback handler
    # would otherwise leave the Telegram spinner stuck because
    # `callback.answer()` never fires. Catch here, dismiss the spinner,
    # and let the logger record the real stack trace.
    @dp.errors()
    async def _on_handler_error(event: ErrorEvent) -> bool:
        logger.exception("handler error", exc_info=event.exception)
        update = event.update
        if update is not None and update.callback_query is not None:
            with contextlib.suppress(Exception):
                await update.callback_query.answer(
                    "Что-то пошло не так. Попробуй ещё раз или напиши /start.",
                    show_alert=False,
                )
        return True

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

    # FastAPI side serves /health, /metrics and /api/v1/* on $PORT; uvicorn
    # runs as an asyncio task in the same event loop as the aiogram
    # polling loop. One container, two surfaces, shared DB + metrics.
    port = int(os.environ.get("PORT", "8080"))
    web_app = create_app()
    web_config = uvicorn.Config(
        web_app,
        host="0.0.0.0",  # noqa: S104
        port=port,
        log_level="info",
        access_log=False,
    )
    web_server = uvicorn.Server(web_config)
    web_task = asyncio.create_task(web_server.serve(), name="convioo-web")
    logger.info("🌐 Web API listening on 0.0.0.0:%d", port)

    logger.info("🚀 Entering polling loop — bot is now live")
    try:
        await dp.start_polling(bot)
    finally:
        logger.info("🛑 Polling stopped, shutting down web + bot")
        web_server.should_exit = True
        with contextlib.suppress(Exception):
            await asyncio.wait_for(web_task, timeout=10)
        await bot.session.close()
