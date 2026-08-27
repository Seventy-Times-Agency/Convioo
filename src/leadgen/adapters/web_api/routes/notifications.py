"""``/api/v1/users/me/notifications`` — digest + reply-tracking opt-ins.

Carved out of ``app.py`` so the cron-driven notification surface lives
next to its sibling services (``core/services/notification_prefs.py``,
``core/services/digest.py``, ``core/services/email_reply_tracker.py``)
rather than buried inside the monolithic FastAPI factory.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from leadgen.adapters.web_api.auth import get_current_user
from leadgen.adapters.web_api.schemas import (
    NotificationPrefsResponse,
    NotificationPrefsUpdate,
)
from leadgen.core.services.notification_prefs import (
    get_prefs,
    update_prefs,
)
from leadgen.db.models import User
from leadgen.db.session import session_factory

router = APIRouter(tags=["notifications"])


@router.get(
    "/api/v1/users/me/notifications",
    response_model=NotificationPrefsResponse,
)
async def get_notification_prefs(
    current_user: User = Depends(get_current_user),
) -> NotificationPrefsResponse:
    """Read the user's digest + reply-tracking opt-ins.

    Both flags default to False. The Settings → Notifications page
    polls this on mount so the toggles render in the right state.
    """
    async with session_factory() as session:
        prefs = await get_prefs(session, current_user.id)
    return NotificationPrefsResponse(
        daily_digest_enabled=prefs.daily_digest_enabled,
        email_reply_tracking_enabled=prefs.email_reply_tracking_enabled,
        email_reply_last_checked_at=prefs.email_reply_last_checked_at,
    )


@router.patch(
    "/api/v1/users/me/notifications",
    response_model=NotificationPrefsResponse,
)
async def update_notification_prefs(
    body: NotificationPrefsUpdate,
    current_user: User = Depends(get_current_user),
) -> NotificationPrefsResponse:
    """Toggle digest and / or reply-tracking opt-ins.

    Patch-style: only fields the caller sends are updated. Both
    toggles are independent — a user can want the digest but not the
    reply scanner, or vice versa.
    """
    async with session_factory() as session:
        prefs = await update_prefs(
            session,
            current_user.id,
            daily_digest_enabled=body.daily_digest_enabled,
            email_reply_tracking_enabled=body.email_reply_tracking_enabled,
        )
    return NotificationPrefsResponse(
        daily_digest_enabled=prefs.daily_digest_enabled,
        email_reply_tracking_enabled=prefs.email_reply_tracking_enabled,
        email_reply_last_checked_at=prefs.email_reply_last_checked_at,
    )
