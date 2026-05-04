"""User notification preferences — read + patch.

Tiny service so the FastAPI route handler doesn't have to know about
SQLAlchemy column names. Keeping this thin lets the worker reuse the
same ``get_users_with_digest_enabled`` helper without dragging the web
adapter along.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.db.models import User


@dataclass(slots=True)
class NotificationPrefs:
    daily_digest_enabled: bool
    email_reply_tracking_enabled: bool
    email_reply_last_checked_at: datetime | None


async def get_prefs(session: AsyncSession, user_id: int) -> NotificationPrefs:
    user = await session.get(User, user_id)
    if user is None:
        # Caller would normally have already verified the user via
        # get_current_user; this branch is defensive against direct
        # invocation.
        raise ValueError(f"user {user_id} not found")
    return NotificationPrefs(
        daily_digest_enabled=bool(user.daily_digest_enabled),
        email_reply_tracking_enabled=bool(
            user.email_reply_tracking_enabled
        ),
        email_reply_last_checked_at=user.email_reply_last_checked_at,
    )


async def update_prefs(
    session: AsyncSession,
    user_id: int,
    *,
    daily_digest_enabled: bool | None = None,
    email_reply_tracking_enabled: bool | None = None,
) -> NotificationPrefs:
    user = await session.get(User, user_id)
    if user is None:
        raise ValueError(f"user {user_id} not found")
    if daily_digest_enabled is not None:
        user.daily_digest_enabled = bool(daily_digest_enabled)
    if email_reply_tracking_enabled is not None:
        user.email_reply_tracking_enabled = bool(email_reply_tracking_enabled)
    await session.commit()
    await session.refresh(user)
    return NotificationPrefs(
        daily_digest_enabled=bool(user.daily_digest_enabled),
        email_reply_tracking_enabled=bool(
            user.email_reply_tracking_enabled
        ),
        email_reply_last_checked_at=user.email_reply_last_checked_at,
    )


async def list_users_with_digest_enabled(
    session: AsyncSession,
) -> list[User]:
    """Workers' lookup — every user opted into the daily digest."""
    rows = (
        await session.execute(
            select(User).where(User.daily_digest_enabled.is_(True))
        )
    ).scalars().all()
    return list(rows)


async def list_users_with_reply_tracking(
    session: AsyncSession,
) -> list[User]:
    """Workers' lookup — every user opted into reply tracking."""
    rows = (
        await session.execute(
            select(User).where(User.email_reply_tracking_enabled.is_(True))
        )
    ).scalars().all()
    return list(rows)
