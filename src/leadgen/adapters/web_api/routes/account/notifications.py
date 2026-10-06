"""Notifications: the in-app feed (``/api/v1/notifications``, the bell)
and the digest + reply-tracking opt-ins (``/api/v1/users/me/notifications``).

Carved out of ``app.py`` so the cron-driven notification surface lives
next to its sibling services (``core/services/notification_prefs.py``,
``core/services/digest.py``, ``core/services/email_reply_tracker.py``)
rather than buried inside the monolithic FastAPI factory.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update

from leadgen.adapters.web_api.auth import get_current_user
from leadgen.adapters.web_api.schemas import (
    NotificationPrefsResponse,
    NotificationPrefsUpdate,
)
from leadgen.core.services.account.notification_prefs import (
    get_prefs,
    update_prefs,
)
from leadgen.db.models import Notification, User
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

    Digest defaults to off, reply tracking to on. The Settings → Notifications page
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


# ── in-app feed (the bell) ─────────────────────────────────────────────


class NotificationOut(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    body: str | None
    link: str | None
    important: bool
    created_at: datetime
    read: bool


class NotificationFeed(BaseModel):
    items: list[NotificationOut]
    unread: int
    unread_important: int


class UnreadCount(BaseModel):
    unread: int
    unread_important: int


class MarkRead(BaseModel):
    ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)
    all: bool = False


async def _unread(session, user_id: int) -> UnreadCount:
    total, important = (
        await session.execute(
            select(
                func.count(Notification.id),
                func.count(Notification.id).filter(Notification.important.is_(True)),
            )
            .where(Notification.user_id == user_id)
            .where(Notification.read_at.is_(None))
        )
    ).one()
    return UnreadCount(unread=int(total or 0), unread_important=int(important or 0))


@router.get("/api/v1/notifications", response_model=NotificationFeed)
async def list_notifications(
    important: bool = False,
    limit: int = Query(default=30, ge=1, le=100),
    current_user: User = Depends(get_current_user),
) -> NotificationFeed:
    """The caller's feed, newest first. ``important`` — only what needs
    action (the default tab)."""
    async with session_factory() as session:
        stmt = (
            select(Notification)
            .where(Notification.user_id == current_user.id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
        if important:
            stmt = stmt.where(Notification.important.is_(True))
        rows = (await session.execute(stmt)).scalars().all()
        counts = await _unread(session, current_user.id)
    return NotificationFeed(
        items=[
            NotificationOut(
                id=n.id,
                kind=n.kind,
                title=n.title,
                body=n.body,
                link=n.link,
                important=n.important,
                # Время всегда с часовым поясом: иначе браузер читает
                # его как местное и «2 мин назад» превращается в «только что».
                created_at=(
                    n.created_at
                    if n.created_at.tzinfo is not None
                    else n.created_at.replace(tzinfo=timezone.utc)
                ),
                read=n.read_at is not None,
            )
            for n in rows
        ],
        unread=counts.unread,
        unread_important=counts.unread_important,
    )


@router.get("/api/v1/notifications/unread", response_model=UnreadCount)
async def unread_notifications(
    current_user: User = Depends(get_current_user),
) -> UnreadCount:
    """Cheap poll for the bell badge."""
    async with session_factory() as session:
        return await _unread(session, current_user.id)


@router.post("/api/v1/notifications/read", response_model=UnreadCount)
async def mark_notifications_read(
    body: MarkRead,
    current_user: User = Depends(get_current_user),
) -> UnreadCount:
    """Mark the given ids (or everything with ``all``) as read."""
    async with session_factory() as session:
        stmt = (
            update(Notification)
            .where(Notification.user_id == current_user.id)
            .where(Notification.read_at.is_(None))
            .values(read_at=datetime.now(timezone.utc))
        )
        if not body.all:
            if not body.ids:
                return await _unread(session, current_user.id)
            stmt = stmt.where(Notification.id.in_(body.ids))
        await session.execute(stmt)
        await session.commit()
        return await _unread(session, current_user.id)
