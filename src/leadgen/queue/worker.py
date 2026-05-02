"""arq worker settings.

Run with ``arq leadgen.queue.worker.WorkerSettings`` in a dedicated
Railway service. Web searches use ``BrokerProgressSink`` +
``WebDeliverySink`` so the SSE endpoint has something to stream.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from arq.connections import RedisSettings

from leadgen.config import get_settings
from leadgen.db.models import SearchQuery
from leadgen.db.session import session_factory
from leadgen.pipeline.search import run_search_with_sinks

logger = logging.getLogger(__name__)


async def run_search_job(
    ctx: dict[str, Any],
    query_id_str: str,
    chat_id: int | None,
    user_profile: dict[str, Any] | None,
) -> None:
    """arq entry point — runs the web search pipeline.

    ``chat_id`` is kept in the signature for backwards compatibility
    with already-enqueued jobs that include it; new code passes None.
    """
    del chat_id  # legacy field from the Telegram era; ignored.
    query_id = uuid.UUID(query_id_str)

    async with session_factory() as session:
        query = await session.get(SearchQuery, query_id)
        if query is None:
            logger.error("run_search_job: query %s not found", query_id)
            return

    from leadgen.adapters.web_api.sinks import WebDeliverySink
    from leadgen.core.services import default_broker
    from leadgen.core.services.progress_broker import BrokerProgressSink

    progress = BrokerProgressSink(default_broker, query_id)
    delivery = WebDeliverySink(query_id)
    await run_search_with_sinks(
        query_id=query_id,
        progress=progress,
        delivery=delivery,
        user_profile=user_profile,
    )


async def _on_startup(_ctx: dict[str, Any]) -> None:
    """Configure structlog before workers start handling jobs."""
    from leadgen.core.services.log_setup import configure_logging

    configure_logging(level=get_settings().log_level)
    logger.info("arq worker booted")


class WorkerSettings:
    """arq ``WorkerSettings`` — discovered via the ``arq`` CLI."""

    functions = [run_search_job]  # noqa: RUF012 — arq API requires a list attr
    redis_settings = RedisSettings.from_dsn(
        get_settings().redis_url or "redis://localhost:6379"
    )
    on_startup = _on_startup
    max_jobs = 5
    job_timeout = 15 * 60
    keep_result = 3600
