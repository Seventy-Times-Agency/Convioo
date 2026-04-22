from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from leadgen.bot.handlers import router
from leadgen.bot.middlewares import DbSessionMiddleware
from leadgen.config import settings
from leadgen.db.session import init_db, session_factory
from leadgen.pipeline import recover_stale_queries

logger = logging.getLogger(__name__)


async def run() -> None:
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

    logger.info("Initialising database")
    await init_db()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.middleware(DbSessionMiddleware(session_factory))
    dp.include_router(router)

    try:
        recovered = await recover_stale_queries(bot)
        if recovered:
            logger.warning("Startup recovery: %d stale queries marked as failed", recovered)
    except Exception:  # noqa: BLE001
        logger.exception("Startup recovery failed; continuing anyway")

    logger.info("Starting polling")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
