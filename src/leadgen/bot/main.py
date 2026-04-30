from __future__ import annotations

import asyncio
import logging
import os

import uvicorn

from leadgen.adapters.web_api import create_app
from leadgen.config import get_settings
from leadgen.db.session import init_db
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

    # Mark any queries that were in-flight when the process last died so
    # they don't stay orphaned as "pending" / "running" forever.
    try:
        recovered = await recover_stale_queries()
        if recovered:
            logger.warning(
                "Startup recovery: %d stale queries marked as failed", recovered
            )
        else:
            logger.info("Startup recovery: no stale queries")
    except Exception:
        logger.exception("Startup recovery failed; continuing anyway")

    # FastAPI serves /health, /metrics and /api/v1/* on $PORT.
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
    logger.info("🌐 Web API listening on 0.0.0.0:%d", port)

    await web_server.serve()
