"""arq worker settings.

Run with ``arq leadgen.queue.worker.WorkerSettings`` in a dedicated
Railway service. Web searches use ``BrokerProgressSink`` +
``WebDeliverySink`` so the SSE endpoint has something to stream.

Beyond search jobs, this worker also runs the recurring outreach-loop
tasks introduced in the post-merge fix-up:

* :func:`cron_daily_digest` — once a day at 09:00 UTC, emails an
  opt-in summary of the previous 24 hours of CRM activity.
* :func:`cron_email_reply_scan` — every 5 minutes, polls Gmail for
  replies to messages we sent on the user's behalf and logs them as
  ``LeadActivity(kind="email_replied")``.

Both tasks no-op cleanly when the user hasn't toggled the relevant
preference, so the worker is idle for users who never enabled them.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from arq import cron
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


async def cron_daily_digest(_ctx: dict[str, Any]) -> int:
    """Cron tick — sends the daily digest to every opted-in user.

    Runs once per day at 09:00 UTC. Returns the number of digests
    actually delivered (a user with no activity is skipped). The whole
    fan-out swallows per-user errors so one bad token doesn't stall
    the rest of the batch.
    """
    from leadgen.core.services.digest import run_daily_digest_for_all_users

    settings = get_settings()
    async with session_factory() as session:
        try:
            sent = await run_daily_digest_for_all_users(
                session, app_url=settings.public_app_url
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("daily_digest: cron crashed err=%s", exc)
            return 0
    logger.info("daily_digest: cron delivered=%d", sent)
    return sent


async def cron_email_reply_scan(_ctx: dict[str, Any]) -> int:
    """Cron tick — polls Gmail for replies to outbound emails.

    Runs every 5 minutes. Skips users who haven't opted into reply
    tracking and users whose Gmail OAuth token is no longer fresh.
    Returns the number of new ``email_replied`` activities recorded
    across all users.
    """
    from leadgen.core.services.email_reply_tracker import (
        scan_replies_for_user,
    )
    from leadgen.core.services.notification_prefs import (
        list_users_with_reply_tracking,
    )
    from leadgen.core.services.oauth_store import (
        OAuthStoreError,
        ensure_fresh_token,
    )

    total = 0
    async with session_factory() as session:
        users = await list_users_with_reply_tracking(session)
        for user in users:
            try:
                fresh = await ensure_fresh_token(
                    session, user_id=user.id, provider="gmail"
                )
            except OAuthStoreError as exc:
                logger.info(
                    "reply_tracker: skip user_id=%s reason=%s",
                    user.id,
                    exc,
                )
                continue
            try:
                count = await scan_replies_for_user(
                    session, user, access_token=fresh.access_token
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "reply_tracker: user_id=%s crashed err=%s",
                    user.id,
                    exc,
                )
                continue
            total += count
    if total:
        logger.info("reply_tracker: tick recorded=%d", total)
    return total


async def _on_startup(_ctx: dict[str, Any]) -> None:
    """Configure structlog + Sentry before workers start handling jobs."""
    from leadgen.core.services.log_setup import configure_logging
    from leadgen.core.services.sentry_setup import configure_sentry

    configure_logging(level=get_settings().log_level)
    try:
        configure_sentry()
    except Exception:  # noqa: BLE001
        logger.warning("worker sentry init crashed", exc_info=True)
    logger.info("arq worker booted")


class WorkerSettings:
    """arq ``WorkerSettings`` — discovered via the ``arq`` CLI."""

    functions = [run_search_job]  # noqa: RUF012 — arq API requires a list attr
    # Cron jobs the worker runs on a schedule. arq's ``cron`` helper
    # locks each tick to a single replica so two workers don't both
    # send the same digest.
    cron_jobs = [  # noqa: RUF012 — arq API requires a list attr
        cron(cron_daily_digest, hour={9}, minute={0}, run_at_startup=False),
        cron(
            cron_email_reply_scan,
            minute=set(range(0, 60, 5)),
            run_at_startup=False,
        ),
    ]
    redis_settings = RedisSettings.from_dsn(
        get_settings().redis_url or "redis://localhost:6379"
    )
    on_startup = _on_startup
    max_jobs = 5
    job_timeout = 15 * 60
    keep_result = 3600
