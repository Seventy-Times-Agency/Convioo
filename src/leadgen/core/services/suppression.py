"""Recipient-level email suppression (do-not-contact list).

Framework-agnostic helpers used by the outreach send paths and the
suppression management API. Keyed on a normalized email so the same
business address re-scraped in a later search stays suppressed.
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.db.models import EmailSuppression


def normalize_email(email: str | None) -> str:
    """Lowercase + trim so comparisons are case/whitespace-insensitive."""
    return (email or "").strip().lower()


async def is_suppressed(
    session: AsyncSession, *, user_id: int, email: str | None
) -> bool:
    """True if this user has suppressed (opted-out) the given recipient."""
    normalized = normalize_email(email)
    if not normalized:
        return False
    row = await session.execute(
        select(EmailSuppression.id).where(
            EmailSuppression.user_id == user_id,
            EmailSuppression.email == normalized,
        )
    )
    return row.first() is not None


async def add_suppression(
    session: AsyncSession,
    *,
    user_id: int,
    email: str | None,
    reason: str | None = None,
    source: str | None = None,
) -> EmailSuppression | None:
    """Idempotently add a recipient to the user's do-not-contact list.

    Returns the existing row if already suppressed (no duplicate insert),
    otherwise the newly created row. Returns None for an empty email.
    """
    normalized = normalize_email(email)
    if not normalized:
        return None
    existing = await session.execute(
        select(EmailSuppression).where(
            EmailSuppression.user_id == user_id,
            EmailSuppression.email == normalized,
        )
    )
    found = existing.scalar_one_or_none()
    if found is not None:
        return found
    row = EmailSuppression(
        user_id=user_id,
        email=normalized,
        reason=(reason or None),
        source=(source or None),
    )
    session.add(row)
    await session.flush()
    return row


async def remove_suppression(
    session: AsyncSession, *, user_id: int, email: str | None
) -> bool:
    """Remove a recipient from the list. True if a row was deleted."""
    normalized = normalize_email(email)
    if not normalized:
        return False
    result = await session.execute(
        delete(EmailSuppression).where(
            EmailSuppression.user_id == user_id,
            EmailSuppression.email == normalized,
        )
    )
    return (result.rowcount or 0) > 0


async def list_suppressions(
    session: AsyncSession, *, user_id: int
) -> list[EmailSuppression]:
    """All suppressed recipients for a user, newest first."""
    result = await session.execute(
        select(EmailSuppression)
        .where(EmailSuppression.user_id == user_id)
        .order_by(EmailSuppression.created_at.desc())
    )
    return list(result.scalars().all())
