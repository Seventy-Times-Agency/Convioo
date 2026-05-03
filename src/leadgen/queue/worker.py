"""arq worker settings.

Run with ``arq leadgen.queue.worker.WorkerSettings`` in a dedicated
Railway service. Web searches use ``BrokerProgressSink`` +
``WebDeliverySink`` so the SSE endpoint has something to stream.

Periodic / cron jobs:
- check_email_replies: every 5 min — scans Gmail inboxes for replies
  to outbound messages and creates LeadActivity(kind="email_replied").
- send_daily_digest: daily at 09:00 UTC — sends a morning summary
  email to every user who enabled notify_daily_digest.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from arq.connections import RedisSettings
from arq.cron import cron

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


async def check_email_replies(ctx: dict[str, Any]) -> None:
    """Poll Gmail inboxes for replies to tracked outbound messages.

    For every user with a connected Gmail credential, fetch messages
    from the last 24 hours and check their ``In-Reply-To`` header
    against ``LeadActivity.payload.message_id`` rows with
    kind="email_sent". When a match is found, insert a new
    LeadActivity(kind="email_replied") and optionally advance the
    lead status to "replied".

    Runs every 5 minutes as an arq cron job. Failures for one user
    are logged and skipped so other users are not affected.
    """
    from sqlalchemy import select, and_

    from leadgen.core.services.oauth_store import (
        OAuthStoreError,
        ensure_fresh_token,
    )
    from leadgen.core.services.secrets_vault import decrypt
    from leadgen.db.models import (
        LeadActivity,
        Lead,
        OAuthCredential,
        User,
    )
    from leadgen.integrations.gmail import (
        GmailError,
        list_inbox_messages,
        get_message_headers,
    )

    since_dt = datetime.now(timezone.utc) - timedelta(hours=24)
    since_str = since_dt.strftime("newer_than:1d")

    async with session_factory() as session:
        # Fetch all users with an active Gmail credential.
        gmail_creds = (
            await session.execute(
                select(OAuthCredential).where(
                    OAuthCredential.provider == "gmail"
                )
            )
        ).scalars().all()

        for cred in gmail_creds:
            user_id = cred.user_id
            try:
                fresh = await ensure_fresh_token(
                    session, user_id=user_id, provider="gmail"
                )
            except OAuthStoreError as exc:
                logger.debug(
                    "check_email_replies: skip user %s — %s", user_id, exc
                )
                continue

            # Fetch sent message ids tracked in LeadActivity for this user.
            sent_rows = (
                await session.execute(
                    select(LeadActivity).where(
                        and_(
                            LeadActivity.user_id == user_id,
                            LeadActivity.kind == "email_sent",
                            LeadActivity.created_at >= since_dt,
                        )
                    )
                )
            ).scalars().all()
            if not sent_rows:
                continue

            # Build lookup: gmail_message_id → LeadActivity row
            id_to_activity: dict[str, LeadActivity] = {}
            for row in sent_rows:
                mid = (row.payload or {}).get("message_id")
                if mid:
                    id_to_activity[mid] = row

            if not id_to_activity:
                continue

            # Fetch inbox messages from the last day.
            try:
                stubs = await list_inbox_messages(
                    fresh.access_token, query="in:inbox newer_than:1d"
                )
            except GmailError as exc:
                logger.warning(
                    "check_email_replies: gmail list failed for user %s: %s",
                    user_id,
                    exc,
                )
                continue

            for stub in stubs:
                msg_id = stub.get("id")
                if not msg_id:
                    continue
                try:
                    headers = await get_message_headers(
                        fresh.access_token,
                        msg_id,
                        headers=("In-Reply-To", "References"),
                    )
                except GmailError:
                    continue

                in_reply_to = headers.get("in-reply-to", "")
                references = headers.get("references", "")

                # Check if any of our sent message ids appear.
                matched: LeadActivity | None = None
                for sent_mid, sent_row in id_to_activity.items():
                    if sent_mid and (
                        sent_mid in in_reply_to or sent_mid in references
                    ):
                        matched = sent_row
                        break

                if matched is None:
                    continue

                # Avoid duplicate replied entries: skip if one already exists.
                existing = (
                    await session.execute(
                        select(LeadActivity).where(
                            and_(
                                LeadActivity.lead_id == matched.lead_id,
                                LeadActivity.kind == "email_replied",
                            )
                        )
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    continue

                now = datetime.now(timezone.utc)
                reply_activity = LeadActivity(
                    lead_id=matched.lead_id,
                    user_id=user_id,
                    kind="email_replied",
                    payload={
                        "gmail_message_id": msg_id,
                        "in_reply_to": in_reply_to,
                    },
                    created_at=now,
                )
                session.add(reply_activity)

                # Auto-advance lead status to "replied" if it's still in
                # an early stage (new or contacted).
                lead = await session.get(Lead, matched.lead_id)
                if lead is not None and lead.lead_status in ("new", "contacted"):
                    lead.lead_status = "replied"
                    lead.last_touched_at = now

                logger.info(
                    "check_email_replies: reply detected for lead %s (user %s)",
                    matched.lead_id,
                    user_id,
                )

        await session.commit()


async def send_daily_digest(ctx: dict[str, Any]) -> None:
    """Send a morning summary to opted-in users.

    Counts per user for the past 24 hours:
    - new leads added
    - hot leads (ai_score >= 80)
    - email replies received

    Skips sending if all counts are zero (nothing to report).
    """
    from sqlalchemy import select, func, and_

    from leadgen.core.services.email_sender import render_daily_digest_email, send_email
    from leadgen.db.models import Lead, LeadActivity, SearchQuery, User

    since_dt = datetime.now(timezone.utc) - timedelta(hours=24)

    async with session_factory() as session:
        opted_in = (
            await session.execute(
                select(User).where(User.notify_daily_digest.is_(True))
            )
        ).scalars().all()

        for user in opted_in:
            if not user.email:
                continue

            # Count new leads via search_queries → leads join (leads have
            # no direct user_id; the link goes through the query).
            new_count_row = await session.execute(
                select(func.count())
                .select_from(Lead)
                .join(SearchQuery, Lead.query_id == SearchQuery.id)
                .where(
                    and_(
                        SearchQuery.user_id == user.id,
                        Lead.created_at >= since_dt,
                        Lead.deleted_at.is_(None),
                    )
                )
            )
            new_count: int = new_count_row.scalar() or 0

            # Count hot leads (score >= 80) created in the same window.
            hot_count_row = await session.execute(
                select(func.count())
                .select_from(Lead)
                .join(SearchQuery, Lead.query_id == SearchQuery.id)
                .where(
                    and_(
                        SearchQuery.user_id == user.id,
                        Lead.created_at >= since_dt,
                        Lead.deleted_at.is_(None),
                        Lead.score_ai >= 80,
                    )
                )
            )
            hot_count: int = hot_count_row.scalar() or 0

            # Count email replies.
            reply_count_row = await session.execute(
                select(func.count()).select_from(LeadActivity).where(
                    and_(
                        LeadActivity.user_id == user.id,
                        LeadActivity.kind == "email_replied",
                        LeadActivity.created_at >= since_dt,
                    )
                )
            )
            reply_count: int = reply_count_row.scalar() or 0

            if new_count == 0 and hot_count == 0 and reply_count == 0:
                continue

            subject, html = render_daily_digest_email(
                display_name=user.display_name or user.email.split("@")[0],
                new_count=new_count,
                hot_count=hot_count,
                reply_count=reply_count,
            )
            await send_email(
                to=user.email,
                subject=subject,
                html=html,
            )
            logger.info(
                "daily_digest sent to user %s (%d new, %d hot, %d replies)",
                user.id,
                new_count,
                hot_count,
                reply_count,
            )


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

    functions = [run_search_job]  # noqa: RUF012
    cron_jobs = [  # noqa: RUF012
        cron(check_email_replies, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
        cron(send_daily_digest, hour=9, minute=0),
    ]
    redis_settings = RedisSettings.from_dsn(
        get_settings().redis_url or "redis://localhost:6379"
    )
    on_startup = _on_startup
    max_jobs = 5
    job_timeout = 15 * 60
    keep_result = 3600
