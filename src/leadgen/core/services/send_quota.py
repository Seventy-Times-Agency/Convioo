"""Warmup ramp + daily send cap — anti-spam guardrails for outreach.

A brand-new sending mailbox that fires hundreds of cold emails on day
one gets flagged fast. We ramp the daily ceiling up gradually based on
how long the mailbox has been connected, and we count every send
against that ceiling in :class:`leadgen.db.models.EmailDailySend`.

The send path calls :func:`check_and_reserve_send` right before
dispatching: it atomically increments today's counter and refuses once
the cap is hit. :func:`get_send_status` exposes the same numbers
read-only for the deliverability dashboard.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.core.services.oauth_store import get_credential
from leadgen.db.models import EmailDailySend, User

logger = logging.getLogger(__name__)

# Warmup ramp constants. Day 0 (just connected) allows START sends; each
# subsequent connected day adds STEP, capped at MAX.
WARMUP_START = 20
WARMUP_STEP = 10
WARMUP_MAX = 200

# Providers that can actually send on the user's behalf — the warmup
# anchor is whichever of these is connected (most-recently first).
_SENDING_PROVIDERS = ("gmail", "outlook")


def warmup_cap(days_connected: int) -> int:
    """Daily send ceiling for a mailbox connected *days_connected* days ago."""
    if days_connected < 0:
        days_connected = 0
    return min(WARMUP_START + WARMUP_STEP * days_connected, WARMUP_MAX)


@dataclass(slots=True)
class ReserveResult:
    """Outcome of :func:`check_and_reserve_send`."""

    allowed: bool
    cap: int
    sent: int  # count AFTER a successful reservation (else current count)


def _as_utc(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


async def _sending_credential(
    session: AsyncSession, user_id: int
):
    """Return the user's connected sending mailbox credential, or None.

    Picks the most-recently connected of the supported providers so the
    warmup anchor follows whichever mailbox the user actually uses.
    """
    best = None
    for provider in _SENDING_PROVIDERS:
        cred = await get_credential(
            session, user_id=user_id, provider=provider
        )
        if cred is None:
            continue
        if best is None or (
            _as_utc(cred.created_at) or datetime.min.replace(tzinfo=timezone.utc)
        ) > (
            _as_utc(best.created_at) or datetime.min.replace(tzinfo=timezone.utc)
        ):
            best = cred
    return best


async def _days_connected(
    session: AsyncSession, user_id: int, now: datetime
) -> tuple[int, str | None]:
    """Age in days of the connected mailbox; falls back to user.created_at.

    Returns ``(days, provider)`` — ``provider`` is None when no sending
    mailbox is connected and we anchor on account age instead.
    """
    cred = await _sending_credential(session, user_id)
    if cred is not None:
        anchor = _as_utc(cred.created_at)
        provider = cred.provider
    else:
        user = await session.get(User, user_id)
        anchor = _as_utc(user.created_at) if user is not None else None
        provider = None
    if anchor is None:
        return 0, provider
    delta = now - anchor
    return max(delta.days, 0), provider


async def check_and_reserve_send(
    session: AsyncSession, user_id: int
) -> ReserveResult:
    """Reserve one send against today's cap. Increments on success.

    Reads-or-creates the ``email_daily_sends`` row for (user, today UTC),
    compares ``sent_count`` against the warmup cap, and — when there's
    headroom — increments and returns ``allowed=True``. Sends are
    serialized by the worker so a get-or-create + increment + flush is
    race-safe enough here; no dialect-specific upsert needed.
    """
    now = datetime.now(timezone.utc)
    today = now.date()
    days, _provider = await _days_connected(session, user_id, now)
    cap = warmup_cap(days)

    row = (
        await session.execute(
            select(EmailDailySend)
            .where(EmailDailySend.user_id == user_id)
            .where(EmailDailySend.send_date == today)
        )
    ).scalar_one_or_none()

    if row is None:
        row = EmailDailySend(user_id=user_id, send_date=today, sent_count=0)
        session.add(row)
        await session.flush()

    if row.sent_count >= cap:
        return ReserveResult(allowed=False, cap=cap, sent=row.sent_count)

    row.sent_count += 1
    row.updated_at = now
    await session.flush()
    return ReserveResult(allowed=True, cap=cap, sent=row.sent_count)


async def get_send_status(
    session: AsyncSession, user_id: int
) -> dict:
    """Read-only daily-cap snapshot for the deliverability dashboard.

    Shape::

        {
          "connected": bool,
          "provider": str | None,
          "warmup_day": int,
          "daily_cap": int,
          "sent_today": int,
          "remaining": int,
        }
    """
    now = datetime.now(timezone.utc)
    today = now.date()
    days, provider = await _days_connected(session, user_id, now)
    cap = warmup_cap(days)

    row = (
        await session.execute(
            select(EmailDailySend)
            .where(EmailDailySend.user_id == user_id)
            .where(EmailDailySend.send_date == today)
        )
    ).scalar_one_or_none()
    sent = int(row.sent_count) if row is not None else 0

    return {
        "connected": provider is not None,
        "provider": provider,
        "warmup_day": days,
        "daily_cap": cap,
        "sent_today": sent,
        "remaining": max(cap - sent, 0),
    }
