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


def _wrap_html(*, heading: str, body_html: str) -> str:
    """Shared shell for every transactional email so the look stays consistent."""
    return f"""
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
margin-bottom:8px;">{heading}</div>
      {body_html}
    </div>
  </body>
</html>
""".strip()


def _button_html(*, href: str, label: str) -> str:
    return f"""
      <p style="margin: 26px 0;">
        <a href="{href}"
           style="display:inline-block; background:#10B5B0; \
color:white; text-decoration:none; padding:11px 22px; \
border-radius:10px; font-weight:600; font-size:14px;">{label}</a>
      </p>
      <p style="font-size:12px; color:#94a3b8; line-height:1.5;">
        Если кнопка не работает, скопируйте ссылку:<br/>
        <a href="{href}" style="color:#10B5B0; \
word-break:break-all;">{href}</a>
      </p>
""".strip()


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
    body = (
        '<p style="color:#475569; line-height:1.55; font-size:14.5px;">'
        "Чтобы закончить регистрацию в Convioo, подтвердите свой email, "
        "нажав кнопку ниже. Ссылка действует 24&nbsp;часа.</p>"
        + _button_html(href=verify_url, label="Подтвердить email")
        + '<p style="font-size:12px; color:#94a3b8; margin-top:24px;">'
        "Если вы не регистрировались в Convioo — просто проигнорируйте "
        "это письмо.</p>"
    )
    return _wrap_html(heading=f"Привет, {name}!", body_html=body), text


def render_password_reset_email(
    *, name: str, reset_url: str
) -> tuple[str, str]:
    """Email a user clicked 'Forgot password' on their account."""
    text = (
        f"Привет, {name}!\n\n"
        "Кто-то (надеемся, вы) запросил сброс пароля для аккаунта Convioo. "
        f"Чтобы задать новый пароль, перейдите по ссылке:\n{reset_url}\n\n"
        "Ссылка действует 1 час. Если это были не вы — просто "
        "проигнорируйте письмо, ваш пароль не изменится.\n\n"
        "— Команда Convioo"
    )
    body = (
        '<p style="color:#475569; line-height:1.55; font-size:14.5px;">'
        "Кто-то (надеемся, вы) запросил сброс пароля для вашего аккаунта "
        "Convioo. Чтобы задать новый пароль, нажмите кнопку ниже. "
        "Ссылка действует 1&nbsp;час.</p>"
        + _button_html(href=reset_url, label="Сбросить пароль")
        + '<p style="font-size:12px; color:#94a3b8; margin-top:24px;">'
        "Если это были не вы — просто проигнорируйте письмо. Ваш пароль "
        "не изменится.</p>"
    )
    return _wrap_html(heading=f"Привет, {name}!", body_html=body), text


def render_password_changed_email(
    *, name: str, ip: str | None, user_agent: str | None, when_iso: str
) -> tuple[str, str]:
    """Security alert — sent right after a successful password change."""
    where = ip or "неизвестно"
    ua = user_agent or "неизвестно"
    text = (
        f"Привет, {name}!\n\n"
        "Пароль вашего аккаунта Convioo только что был изменён.\n"
        f"Когда: {when_iso}\nIP: {where}\nУстройство: {ua}\n\n"
        "Если это были вы — всё в порядке, можно ничего не делать. "
        "Если нет — немедленно сбросьте пароль через 'Забыли пароль?' "
        "и напишите нам на [email protected].\n\n"
        "— Команда Convioo"
    )
    body = (
        '<p style="color:#475569; line-height:1.55; font-size:14.5px;">'
        "Пароль вашего аккаунта Convioo только что был изменён.</p>"
        '<ul style="color:#475569; font-size:14px; line-height:1.7;">'
        f"<li>Когда: {when_iso}</li><li>IP: {where}</li>"
        f"<li>Устройство: {ua}</li></ul>"
        '<p style="color:#475569; line-height:1.55; font-size:14.5px;">'
        "Если это были не вы — немедленно используйте «Забыли пароль?» "
        "и напишите нам на [email protected].</p>"
    )
    return _wrap_html(heading="Пароль изменён", body_html=body), text


def render_email_recovery_email(
    *, name: str, account_email_masked: str, change_url: str
) -> tuple[str, str]:
    """Reminder of which email the account is registered under."""
    text = (
        f"Привет, {name}!\n\n"
        "Вы запросили напоминание о email от аккаунта Convioo.\n"
        f"Аккаунт зарегистрирован на: {account_email_masked}\n\n"
        "Если хотите сменить email на этот резервный — перейдите по "
        f"ссылке:\n{change_url}\n\n"
        "Ссылка действует 1 час. Если это были не вы — игнорируйте "
        "письмо.\n\n"
        "— Команда Convioo"
    )
    body = (
        '<p style="color:#475569; line-height:1.55; font-size:14.5px;">'
        "Вы запросили напоминание о email от аккаунта Convioo. Аккаунт "
        f"зарегистрирован на:</p><p style=\"font-weight:600; "
        f'color:#1F3D5C; font-size:16px;">{account_email_masked}</p>'
        '<p style="color:#475569; line-height:1.55; font-size:14.5px;">'
        "Если хотите сменить email аккаунта на этот резервный, нажмите "
        "кнопку ниже. Ссылка действует 1&nbsp;час.</p>"
        + _button_html(href=change_url, label="Сменить email на этот")
        + '<p style="font-size:12px; color:#94a3b8; margin-top:24px;">'
        "Если это были не вы — просто проигнорируйте письмо.</p>"
    )
    return _wrap_html(heading=f"Привет, {name}!", body_html=body), text


def render_email_changed_alert(
    *, name: str, new_email_masked: str, when_iso: str
) -> tuple[str, str]:
    """Sent to the OLD address after the user changed their primary email."""
    text = (
        f"Привет, {name}!\n\n"
        f"Email вашего аккаунта Convioo был изменён на: {new_email_masked}.\n"
        f"Когда: {when_iso}\n\n"
        "Если это были не вы — немедленно напишите нам на "
        "[email protected], мы вернём аккаунт.\n\n"
        "— Команда Convioo"
    )
    body = (
        '<p style="color:#475569; line-height:1.55; font-size:14.5px;">'
        "Email вашего аккаунта Convioo был изменён.</p>"
        '<ul style="color:#475569; font-size:14px; line-height:1.7;">'
        f"<li>Новый email: {new_email_masked}</li><li>Когда: {when_iso}</li></ul>"
        '<p style="color:#475569; line-height:1.55; font-size:14.5px;">'
        "Если это были не вы — немедленно напишите нам на "
        "[email protected], мы поможем вернуть аккаунт.</p>"
    )
    return _wrap_html(heading="Email изменён", body_html=body), text


def render_new_device_login_email(
    *, name: str, ip: str | None, user_agent: str | None, when_iso: str
) -> tuple[str, str]:
    where = ip or "неизвестно"
    ua = user_agent or "неизвестно"
    text = (
        f"Привет, {name}!\n\n"
        "В ваш аккаунт Convioo только что вошли с нового устройства.\n"
        f"Когда: {when_iso}\nIP: {where}\nУстройство: {ua}\n\n"
        "Если это были вы — игнорируйте письмо. Если нет — смените "
        "пароль и завершите все сессии в Настройках → Безопасность.\n\n"
        "— Команда Convioo"
    )
    body = (
        '<p style="color:#475569; line-height:1.55; font-size:14.5px;">'
        "В ваш аккаунт Convioo только что вошли с нового устройства.</p>"
        '<ul style="color:#475569; font-size:14px; line-height:1.7;">'
        f"<li>Когда: {when_iso}</li><li>IP: {where}</li>"
        f"<li>Устройство: {ua}</li></ul>"
        '<p style="color:#475569; line-height:1.55; font-size:14.5px;">'
        "Если это были не вы — смените пароль и завершите все сессии в "
        "Настройках → Безопасность.</p>"
    )
    return _wrap_html(heading="Вход с нового устройства", body_html=body), text


def render_account_locked_email(
    *, name: str, unlock_iso: str
) -> tuple[str, str]:
    text = (
        f"Привет, {name}!\n\n"
        "Мы временно заблокировали входы в ваш аккаунт Convioo "
        "после серии неудачных попыток.\n"
        f"Разблокировка: {unlock_iso}\n\n"
        "Если это были не вы — рекомендуем сбросить пароль через "
        "«Забыли пароль?» прямо сейчас.\n\n"
        "— Команда Convioo"
    )
    body = (
        '<p style="color:#475569; line-height:1.55; font-size:14.5px;">'
        "Мы временно заблокировали входы в ваш аккаунт Convioo после "
        "серии неудачных попыток подбора пароля.</p>"
        f'<p style="color:#475569; font-size:14.5px;">'
        f"Разблокировка автоматически: <b>{unlock_iso}</b>.</p>"
        '<p style="color:#475569; line-height:1.55; font-size:14.5px;">'
        "Если это были не вы — рекомендуем сбросить пароль через «Забыли "
        "пароль?» прямо сейчас, чтобы перекрыть атаку.</p>"
    )
    return _wrap_html(heading="Аккаунт временно заблокирован", body_html=body), text


def mask_email(email: str | None) -> str:
    """``[email protected]`` → ``j****[email protected]``."""
    if not email or "@" not in email:
        return "(unknown)"
    local, _, domain = email.partition("@")
    if len(local) <= 1:
        return f"*@{domain}"
    if len(local) <= 3:
        return f"{local[0]}*@{domain}"
    return f"{local[0]}{'*' * 4}{local[-1]}@{domain}"
