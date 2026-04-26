"""Email dispatch via Resend with a log-only fallback.

Resend is the simplest modern transactional email provider — one POST
to ``api.resend.com/emails`` with an API key. We don't pull in the
``resend`` SDK to keep the dependency surface small; one ``httpx``
call covers it.

When ``RESEND_API_KEY`` is empty (typical for local dev or until the
sending domain is verified), ``send_email`` logs the would-be email
to stdout and returns success — so the signup flow keeps working.
The verification URL also lands in the logs, which is enough to
click through and confirm an account during early integration.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from leadgen.config import get_settings

logger = logging.getLogger(__name__)


async def send_email(
    *,
    to: str,
    subject: str,
    html: str,
    text: str | None = None,
) -> bool:
    """Send a transactional email. Returns True on dispatch success.

    The log-only fallback always returns True so callers don't treat
    "no provider configured" as a hard error during local / staging
    runs — the user can still grab the verification link from logs.
    """
    settings = get_settings()
    api_key = settings.resend_api_key.strip()

    if not api_key:
        logger.warning(
            "send_email: RESEND_API_KEY not configured; would have sent to=%s "
            "subject=%r body=\n%s",
            to,
            subject,
            text or html,
        )
        return True

    payload: dict[str, Any] = {
        "from": settings.email_from,
        "to": [to],
        "subject": subject,
        "html": html,
    }
    if text:
        payload["text"] = text

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if response.status_code >= 400:
            logger.error(
                "send_email: Resend returned %s for to=%s body=%s",
                response.status_code,
                to,
                response.text,
            )
            return False
        return True
    except Exception:  # noqa: BLE001
        logger.exception("send_email: dispatch failed for to=%s", to)
        return False


def render_verification_email(
    *, name: str, verify_url: str
) -> tuple[str, str]:
    """Return ``(html, text)`` for the email-verification template."""
    text = (
        f"Привет, {name}!\n\n"
        "Чтобы закончить регистрацию в Convioo, подтвердите email "
        f"по ссылке:\n{verify_url}\n\n"
        "Ссылка действует 24 часа. Если вы не регистрировались — "
        "просто проигнорируйте это письмо.\n\n"
        "— Команда Convioo"
    )
    html = f"""
<!doctype html>
<html>
  <body style="font-family: -apple-system, system-ui, sans-serif; \
background:#f6f7f9; padding:32px;">
    <div style="max-width:520px; margin:0 auto; background:white; \
border-radius:14px; padding:32px 28px; \
box-shadow:0 6px 20px rgba(15,15,20,0.06);">
      <div style="font-weight:700; font-size:18px; \
color:#1F3D5C; margin-bottom:18px;">Convioo</div>
      <div style="font-size:18px; font-weight:700; \
margin-bottom:8px;">Привет, {name}!</div>
      <p style="color:#475569; line-height:1.55; font-size:14.5px;">
        Чтобы закончить регистрацию в Convioo, подтвердите свой email,
        нажав кнопку ниже. Ссылка действует 24&nbsp;часа.
      </p>
      <p style="margin: 26px 0;">
        <a href="{verify_url}"
           style="display:inline-block; background:#10B5B0; \
color:white; text-decoration:none; padding:11px 22px; \
border-radius:10px; font-weight:600; font-size:14px;">
          Подтвердить email
        </a>
      </p>
      <p style="font-size:12px; color:#94a3b8; line-height:1.5;">
        Если кнопка не работает, скопируйте ссылку:<br/>
        <a href="{verify_url}" style="color:#10B5B0; \
word-break:break-all;">{verify_url}</a>
      </p>
      <p style="font-size:12px; color:#94a3b8; margin-top:24px;">
        Если вы не регистрировались в Convioo — просто
        проигнорируйте это письмо.
      </p>
    </div>
  </body>
</html>
""".strip()
    return html, text
