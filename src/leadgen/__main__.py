"""Convioo entrypoint — runs the FastAPI web service.

The Telegram bot was removed; the only surface left here is the
FastAPI app that serves the Next.js frontend on Vercel. A dedicated
arq worker (started separately when REDIS_URL is set) runs background
search jobs.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import traceback


def _configure_logging() -> None:
    """Configure logging to stdout BEFORE any import that might log."""
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def main() -> None:
    _configure_logging()
    logger = logging.getLogger("convioo.__main__")

    commit = (
        os.environ.get("RAILWAY_GIT_COMMIT_SHA")
        or os.environ.get("GIT_COMMIT_SHA")
        or "unknown"
    )[:12]
    branch = os.environ.get("RAILWAY_GIT_BRANCH") or "unknown"
    print("=" * 60, flush=True)
    print(" CONVIOO API: Python process starting", flush=True)
    print(f" Python: {sys.version.split()[0]}", flush=True)
    print(f" Commit: {commit}  Branch: {branch}", flush=True)
    print("=" * 60, flush=True)

    try:
        import uvicorn

        from leadgen.adapters.web_api import create_app
        from leadgen.config import get_settings
        from leadgen.db.session import dispose_engine, init_db
        from leadgen.pipeline import recover_stale_queries

        settings = get_settings()
        logging.getLogger().setLevel(settings.log_level)

        async def _startup() -> None:
            await init_db()
            recovered = await recover_stale_queries()
            if recovered:
                logger.warning("Marked %d stale searches as failed on boot", recovered)
            await dispose_engine()

        asyncio.run(_startup())

        port = int(os.environ.get("PORT", "8080"))
        uvicorn.run(
            create_app(),
            host="0.0.0.0",
            port=port,
            log_level=settings.log_level.lower(),
            access_log=False,
        )
    except KeyboardInterrupt:
        logger.info("Interrupted by user, shutting down")
    except Exception:
        logger.critical("API crashed at top level", exc_info=True)
        traceback.print_exc(file=sys.stdout)
        sys.stdout.flush()
        raise


if __name__ == "__main__":
    main()
