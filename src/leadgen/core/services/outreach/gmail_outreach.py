"""Cold email from the rep's own Gmail — one send path for manual
letters and funnel auto-touches.

Both used to diverge: manual letters went through Gmail with an
unsubscribe header, funnel touches went through the platform's Resend
sender with neither unsubscribe nor reply tracking. Everything that
makes a cold email safe to send lives here: do-not-contact list, the
warmup daily cap, the one-click unsubscribe header, the open pixel and
the Gmail ``threadId`` the reply tracker matches on.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.config import get_settings
from leadgen.core.services.integrations.oauth_store import (
    OAuthStoreError,
    ensure_fresh_token,
)
from leadgen.core.services.integrations.tracking import generate_track_token
from leadgen.core.services.outreach.email_sender import sanitize_email_header
from leadgen.core.services.outreach.send_quota import (
    check_and_reserve_send,
    has_send_headroom,
)
from leadgen.core.services.outreach.suppression import is_suppressed
from leadgen.core.services.outreach.unsubscribe import unsubscribe_url


class OutreachSendError(Exception):
    """Why a letter did not go out.

    ``code`` is one of: ``suppressed``, ``not_connected``, ``no_sender``,
    ``quota``, ``provider``.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(slots=True)
class SentEmail:
    to: str
    subject: str
    message_id: str | None
    thread_id: str | None
    sent_at: datetime


async def send_cold_email(
    session: AsyncSession,
    *,
    user_id: int,
    lead_id: str,
    to: str,
    subject: str,
    body: str,
    fallback_from: str | None = None,
) -> SentEmail:
    """Send one letter from ``user_id``'s Gmail. Raises
    :class:`OutreachSendError` before anything is written; never
    commits — the caller owns the transaction. The warmup counter is
    bumped (flushed) only after Gmail accepted the letter."""
    recipient = sanitize_email_header(to)
    if not recipient:
        raise OutreachSendError("no_recipient", "lead has no email address")
    if await is_suppressed(session, user_id=user_id, email=recipient):
        raise OutreachSendError(
            "suppressed",
            "recipient is on your do-not-contact (suppression) list",
        )
    try:
        fresh = await ensure_fresh_token(
            session, user_id=user_id, provider="gmail"
        )
    except OAuthStoreError as exc:
        raise OutreachSendError("not_connected", str(exc)) from exc
    from_addr = fresh.account_email or fallback_from or ""
    if not from_addr:
        raise OutreachSendError("no_sender", "cannot determine sender address")

    quota = await has_send_headroom(session, user_id)
    if not quota.allowed:
        raise OutreachSendError(
            "quota",
            f"daily warmup limit reached ({quota.sent}/{quota.cap})",
        )

    subject = sanitize_email_header(subject)
    base = get_settings().public_app_url.rstrip("/")
    token = generate_track_token(str(lead_id), str(user_id))
    pixel = f"{base}/api/v1/track/{token}?lead_id={lead_id}&user_id={user_id}"
    # Plain text from the composer or a template: escape it, keep breaks.
    body_html = html.escape(body).replace("\n", "<br>")
    html_body = (
        f"<p>{body_html}</p>"
        f'<img src="{pixel}" width="1" height="1" style="display:none" alt="">'
    )

    from leadgen.integrations.gmail import (
        GmailError,
        build_raw_message,
        send_message,
    )

    raw = build_raw_message(
        from_addr=from_addr,
        to_addr=recipient,
        subject=subject,
        body=body,
        html_body=html_body,
        list_unsubscribe_url=unsubscribe_url(user_id, recipient),
    )
    try:
        resp = await send_message(
            access_token=fresh.access_token, raw_message=raw
        )
    except GmailError as exc:
        raise OutreachSendError("provider", f"gmail send failed: {exc}") from exc
    # Считаем письмо в дневной лимит только после того, как оно ушло.
    await check_and_reserve_send(session, user_id)
    return SentEmail(
        to=recipient,
        subject=subject,
        message_id=resp.get("id"),
        thread_id=resp.get("threadId"),
        sent_at=datetime.now(timezone.utc),
    )
