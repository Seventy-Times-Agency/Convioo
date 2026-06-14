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
from datetime import datetime, timedelta, timezone
from typing import Any

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import select

from leadgen.config import get_settings
from leadgen.db.models import Lead, SearchQuery
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


async def decay_stale_leads(_ctx: dict[str, Any]) -> dict:
    """Cron tick — degrades score_ai for leads untouched for 7+ days.

    Runs once per day at 03:00 UTC. Finds all "new" status leads that
    haven't been touched in the past 7 days and reduces their AI score
    by 10% (multiplies by 0.9). Returns a dict with count of decayed
    leads. No-ops cleanly if no stale leads exist.
    """
    decayed = 0
    async with session_factory() as session:
        try:
            # last_touched_at is tz-aware on Postgres; comparing against a
            # naive cutoff raises on asyncpg and silently breaks the cron.
            cutoff = datetime.now(timezone.utc) - timedelta(days=7)
            result = await session.execute(
                select(Lead)
                .where(Lead.lead_status == "new")
                .where(Lead.last_touched_at < cutoff)
                .where(Lead.score_ai.is_not(None))
            )
            leads = result.scalars().all()
            for lead in leads:
                lead.score_ai = round(lead.score_ai * 0.9, 1)
            await session.commit()
            decayed = len(leads)
        except Exception as exc:  # noqa: BLE001
            logger.warning("decay_stale_leads: cron crashed err=%s", exc)
    if decayed:
        logger.info("decay_stale_leads: cron decayed=%d", decayed)
    return {"decayed": decayed}


async def check_crm_lead_ratings(_ctx: dict[str, Any]) -> dict[str, int]:
    """Weekly cron: re-fetch Google ratings for CRM leads, alert on changes.

    Processes leads with non-new/non-archived status. Appends a snapshot to
    rating_snapshots and fires a Slack alert when rating delta >= 0.3 or
    new_reviews delta > 5.
    """
    from sqlalchemy import and_

    from leadgen.collectors.google_places import GooglePlacesCollector
    from leadgen.integrations.slack import _send_slack_notification_async

    settings = get_settings()
    checked = 0
    alerted = 0

    try:
        async with session_factory() as session:
            result = await session.execute(
                select(Lead)
                .where(
                    and_(
                        Lead.lead_status.not_in(["new", "archived"]),
                        Lead.source == "google_places",
                        Lead.source_id.isnot(None),
                    )
                )
                .limit(200)
            )
            leads = list(result.scalars().all())

        collector = GooglePlacesCollector(api_key=settings.google_places_api_key)

        for lead in leads:
            try:
                details = await collector.get_details(lead.source_id)
                if not details:
                    continue

                new_rating: float | None = details.get("rating")
                new_reviews: int | None = (
                    details.get("userRatingCount") or details.get("reviews_count")
                )
                if new_rating is None:
                    continue

                old_rating = lead.rating or new_rating
                old_reviews = lead.reviews_count or 0
                rating_delta = abs(new_rating - old_rating)
                reviews_delta = (new_reviews or 0) - old_reviews
                should_alert = rating_delta >= 0.3 or reviews_delta > 5
                checked += 1

                snapshot = {
                    "date": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                    "rating": new_rating,
                    "reviews_count": new_reviews or 0,
                }

                async with session_factory() as session:
                    db_lead = await session.get(Lead, lead.id)
                    if db_lead is None:
                        continue
                    db_lead.rating_snapshots = list(db_lead.rating_snapshots or []) + [snapshot]
                    db_lead.rating = new_rating
                    if new_reviews is not None:
                        db_lead.reviews_count = new_reviews
                    await session.commit()

                if should_alert and settings.slack_webhook_url:
                    direction = "+" if new_rating >= old_rating else ""
                    text = (
                        f":bar_chart: *Review Alert* — {lead.name}\n"
                        f"Rating: {old_rating} → {new_rating} "
                        f"({direction}{new_rating - old_rating:.1f})\n"
                        f"Reviews: {old_reviews} → {new_reviews or 0} "
                        f"(+{reviews_delta})\n"
                        f"Status: {lead.lead_status}"
                    )
                    await _send_slack_notification_async(text)
                    alerted += 1

            except Exception:
                logger.warning(
                    "check_crm_lead_ratings: failed for lead %s", lead.id, exc_info=True
                )
                continue

    except Exception:
        logger.warning("check_crm_lead_ratings: cron crashed", exc_info=True)

    logger.info("check_crm_lead_ratings: checked=%d alerted=%d", checked, alerted)
    return {"checked": checked, "alerted": alerted}


async def send_sequence_step(
    _ctx: dict[str, Any], enrollment_id: str
) -> dict:
    """Send one step of a follow-up sequence and schedule the next step."""
    from leadgen.core.services.email_sender import send_email
    from leadgen.db.models import (
        EmailSequence,
        SequenceEnrollment,
        User,
    )

    try:
        enrollment_uuid = uuid.UUID(enrollment_id)
        async with session_factory() as session:
            enrollment = await session.get(SequenceEnrollment, enrollment_uuid)
            if enrollment is None or enrollment.status != "active":
                return {"skipped": True}

            seq = await session.get(EmailSequence, enrollment.sequence_id)
            lead = await session.get(Lead, enrollment.lead_id)
            user = await session.get(User, enrollment.user_id)

            if not seq or not lead or not user:
                return {"skipped": True}

            steps = seq.steps or []
            step_idx = enrollment.current_step
            if step_idx >= len(steps):
                enrollment.status = "completed"
                await session.commit()
                return {"completed": True}

            step = steps[step_idx]

            # Pull a usable email out of the website-scrape metadata.
            # The collector only populates ``website_meta.emails`` after
            # the enrichment pass, so for a freshly-imported lead this is
            # often missing — pause the enrollment (not fail) so a later
            # enrichment run can pick it back up.
            meta = lead.website_meta if isinstance(lead.website_meta, dict) else {}
            emails_raw = meta.get("emails") if isinstance(meta, dict) else None
            lead_email: str | None = None
            if isinstance(emails_raw, list):
                for candidate in emails_raw:
                    if isinstance(candidate, str) and candidate.strip():
                        lead_email = candidate.strip()
                        break
            if not lead_email:
                enrollment.status = "paused"
                enrollment.next_send_at = None
                await session.commit()
                logger.info(
                    "send_sequence_step: paused enrollment=%s lead=%s — no email",
                    enrollment_id,
                    enrollment.lead_id,
                )
                return {"paused": "no email"}

            subject = step["subject"].replace("{{name}}", lead.name or "")
            body = (
                step["body"]
                .replace("{{name}}", lead.name or "")
                .replace("{{website}}", lead.website or "")
            )

            await send_email(
                to=lead_email,
                subject=subject,
                html=body.replace("\n", "<br>"),
                text=body,
            )

            next_step_idx = step_idx + 1
            if next_step_idx >= len(steps):
                enrollment.status = "completed"
                enrollment.next_send_at = None
            else:
                next_step = steps[next_step_idx]
                delay_days = int(next_step.get("day", 1)) - int(
                    step.get("day", 0)
                )
                if delay_days < 1:
                    delay_days = 1
                next_send = datetime.now(timezone.utc) + timedelta(
                    days=delay_days
                )
                enrollment.current_step = next_step_idx
                enrollment.next_send_at = next_send

                redis = _ctx.get("redis")
                if redis:
                    await redis.enqueue_job(
                        "send_sequence_step",
                        str(enrollment.id),
                        _defer_by=timedelta(days=delay_days),
                    )

            await session.commit()
            return {"sent": True, "step": step_idx}

    except Exception:
        logger.warning(
            "send_sequence_step: failed enrollment_id=%s",
            enrollment_id,
            exc_info=True,
        )
        return {"error": True}


async def cron_check_sequence_enrollments(_ctx: dict[str, Any]) -> dict:
    """Hourly fallback — sweep due enrollments missed by deferred jobs."""
    from datetime import timezone

    from sqlalchemy import and_

    from leadgen.db.models import SequenceEnrollment

    sent = 0
    try:
        now = datetime.now(timezone.utc)
        async with session_factory() as session:
            due = (
                await session.execute(
                    select(SequenceEnrollment)
                    .where(
                        and_(
                            SequenceEnrollment.status == "active",
                            SequenceEnrollment.next_send_at <= now,
                        )
                    )
                    .limit(50)
                )
            ).scalars().all()

        redis = _ctx.get("redis")
        for enrollment in due:
            if redis:
                await redis.enqueue_job(
                    "send_sequence_step", str(enrollment.id)
                )
                sent += 1

    except Exception:
        logger.warning(
            "cron_check_sequence_enrollments: crashed", exc_info=True
        )

    return {"enqueued": sent}


async def _on_startup(_ctx: dict[str, Any]) -> None:
    """Configure structlog + Sentry before workers start handling jobs."""
    from leadgen.config import assert_production_secrets
    from leadgen.core.services.log_setup import configure_logging
    from leadgen.core.services.sentry_setup import configure_sentry

    # Same fail-fast contract as the web app: a Railway worker with
    # missing AUTH_JWT_SECRET / FERNET_KEY must crash, not limp along.
    assert_production_secrets()

    configure_logging(level=get_settings().log_level)
    try:
        configure_sentry()
    except Exception:  # noqa: BLE001
        logger.warning("worker sentry init crashed", exc_info=True)
    logger.info("arq worker booted")


class WorkerSettings:
    """arq ``WorkerSettings`` — discovered via the ``arq`` CLI."""

    functions = [run_search_job, send_sequence_step]  # noqa: RUF012 — arq API requires a list attr
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
        cron(decay_stale_leads, hour={3}, minute={0}, run_at_startup=False),
        cron(
            cron_check_sequence_enrollments,
            minute={0},
            run_at_startup=False,
        ),
        cron(
            check_crm_lead_ratings,
            weekday={6},
            hour={8},
            minute={0},
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
