"""Лента уведомлений внутри приложения (колокольчик в левой панели).

Каждое событие команды сначала пишется сюда — это канал, который есть у
всех. Telegram — дополнительно, если человек его привязал. Срочное
(горячий ответ, просроченный перезвон, 80% бюджета) уходит ещё и на
почту, но только если человек не заходил в Convioo последние 15 минут:
иначе он и так видит колокольчик.

Запись идёт отдельной сессией: уведомление не должно зависеть от
транзакции того, кто его вызвал, и не должно её ронять.
"""

from __future__ import annotations

import html
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select

from leadgen.db.models import Notification, TelegramConnection, User, UserSession
from leadgen.db.session import session_factory

logger = logging.getLogger(__name__)

#: Сколько человек должен отсутствовать, чтобы срочное ушло на почту.
EMAIL_IF_AWAY = timedelta(minutes=15)


async def _away(session, user_id: int, now: datetime) -> bool:
    last = (
        await session.execute(
            select(func.max(UserSession.last_seen_at)).where(
                UserSession.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if last is None:
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return now - last >= EMAIL_IF_AWAY


async def _email(user: User, title: str, body: str | None, link: str | None) -> None:
    from leadgen.config import get_settings
    from leadgen.core.services.outreach.email_sender import send_email

    if not user.email:
        return
    base = get_settings().public_app_url.rstrip("/")
    url = f"{base}{link}" if link else f"{base}/app"
    text = "\n\n".join(filter(None, [title, body, url]))
    body_html = html.escape(body or "").replace("\n", "<br>")
    page = (
        f"<p><b>{html.escape(title)}</b></p>"
        + (f"<p>{body_html}</p>" if body else "")
        + f'<p><a href="{html.escape(url)}">Открыть в Convioo</a></p>'
    )
    await send_email(to=user.email, subject=f"Convioo: {title}", html=page, text=text)


async def _telegram(session, user_id: int, text: str) -> bool:
    conn = (
        await session.execute(
            select(TelegramConnection).where(TelegramConnection.user_id == user_id)
        )
    ).scalar_one_or_none()
    if conn is None:
        return False
    from leadgen.adapters.telegram_v2.api import send_message

    await send_message(conn.chat_id, text)
    return True


async def notify(
    user_id: int,
    *,
    kind: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
    team_id: uuid.UUID | None = None,
    important: bool = False,
    urgent: bool = False,
    payload: dict[str, Any] | None = None,
    telegram_text: str | None = None,
) -> bool:
    """Записать уведомление; продублировать в Telegram и (срочное) на
    почту. Никогда не бросает исключение. True — запись в ленте есть."""
    now = datetime.now(timezone.utc)
    try:
        async with session_factory() as session:
            session.add(
                Notification(
                    user_id=user_id,
                    team_id=team_id,
                    kind=kind,
                    title=title[:255],
                    body=body,
                    link=link,
                    important=important or urgent,
                    payload=payload,
                    created_at=now,
                )
            )
            await session.commit()
            try:
                await _telegram(
                    session,
                    user_id,
                    telegram_text or "\n".join(filter(None, [title, body])),
                )
            except Exception:  # noqa: BLE001
                logger.warning("notify: telegram failed user=%s", user_id, exc_info=True)
            if urgent and await _away(session, user_id, now):
                user = await session.get(User, user_id)
                if user is not None:
                    try:
                        await _email(user, title, body, link)
                    except Exception:  # noqa: BLE001
                        logger.warning("notify: email failed user=%s", user_id, exc_info=True)
        return True
    except Exception:  # noqa: BLE001 — уведомление не роняет поток
        logger.warning("notify failed user=%s kind=%s", user_id, kind, exc_info=True)
        return False
