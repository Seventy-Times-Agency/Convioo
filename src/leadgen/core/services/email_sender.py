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
import re
from html import escape as _esc
from typing import Any

import httpx

from leadgen.config import get_settings
from leadgen.utils.http import request_with_retry
from leadgen.utils.locale_text import normalize_lang, pick

logger = logging.getLogger(__name__)

# Any ASCII control char (incl. CR / LF / TAB / NUL) — these have no
# business inside an email header value and are the vector for header
# (CRLF) injection ("Subject: hi\r\nBcc: evil@x").
_HEADER_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]+")


def sanitize_email_header(value: str | None) -> str:
    """Strip control chars from a value destined for an email header.

    CR / LF (and any other control char) are collapsed to a single
    space so a lead name like ``"Acme\\r\\nBcc: evil@x"`` can't inject
    extra headers into the subject or recipient. The result is trimmed.
    Use this on every subject and ``To`` assembled from lead / user /
    template data before it reaches the transport.
    """
    if not value:
        return ""
    return _HEADER_CONTROL_CHARS.sub(" ", value).strip()


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
            response = await request_with_retry(
                client,
                "POST",
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                source="resend",
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


def _button_html(*, href: str, label: str, lang: str | None = None) -> str:
    fallback_line = pick(
        lang,
        ru="Если кнопка не работает, скопируйте ссылку:",
        uk="Якщо кнопка не працює, скопіюйте посилання:",
        en="If the button doesn't work, copy this link:",
    )
    return f"""
      <p style="margin: 26px 0;">
        <a href="{href}"
           style="display:inline-block; background:#10B5B0; \
color:white; text-decoration:none; padding:11px 22px; \
border-radius:10px; font-weight:600; font-size:14px;">{label}</a>
      </p>
      <p style="font-size:12px; color:#94a3b8; line-height:1.5;">
        {fallback_line}<br/>
        <a href="{href}" style="color:#10B5B0; \
word-break:break-all;">{href}</a>
      </p>
""".strip()


def _greeting(name: str, lang: str | None = None) -> str:
    return pick(
        lang,
        ru=f"Привет, {name}!",
        uk=f"Привіт, {name}!",
        en=f"Hi {name}!",
    )


def render_verification_email(
    *, name: str, verify_url: str, lang: str | None = None
) -> tuple[str, str]:
    """Return ``(html, text)`` for the email-verification template."""
    lang = normalize_lang(lang)
    text = pick(
        lang,
        ru=(
            f"Привет, {name}!\n\n"
            "Чтобы закончить регистрацию в Convioo, подтвердите email "
            f"по ссылке:\n{verify_url}\n\n"
            "Ссылка действует 24 часа. Если вы не регистрировались — "
            "просто проигнорируйте это письмо.\n\n"
            "— Команда Convioo"
        ),
        uk=(
            f"Привіт, {name}!\n\n"
            "Щоб завершити реєстрацію в Convioo, підтвердьте email "
            f"за посиланням:\n{verify_url}\n\n"
            "Посилання дійсне 24 години. Якщо ви не реєструвалися — "
            "просто проігноруйте цей лист.\n\n"
            "— Команда Convioo"
        ),
        en=(
            f"Hi {name}!\n\n"
            "To finish signing up for Convioo, please verify your email "
            f"via this link:\n{verify_url}\n\n"
            "The link is valid for 24 hours. If you didn't sign up, "
            "just ignore this email.\n\n"
            "— The Convioo team"
        ),
    )
    body = (
        '<p style="color:#475569; line-height:1.55; font-size:14.5px;">'
        + pick(
            lang,
            ru=(
                "Чтобы закончить регистрацию в Convioo, подтвердите свой "
                "email, нажав кнопку ниже. Ссылка действует 24&nbsp;часа."
            ),
            uk=(
                "Щоб завершити реєстрацію в Convioo, підтвердьте свій "
                "email, натиснувши кнопку нижче. Посилання дійсне "
                "24&nbsp;години."
            ),
            en=(
                "To finish signing up for Convioo, verify your email by "
                "clicking the button below. The link is valid for "
                "24&nbsp;hours."
            ),
        )
        + "</p>"
        + _button_html(
            href=verify_url,
            label=pick(
                lang,
                ru="Подтвердить email",
                uk="Підтвердити email",
                en="Verify email",
            ),
            lang=lang,
        )
        + '<p style="font-size:12px; color:#94a3b8; margin-top:24px;">'
        + pick(
            lang,
            ru=(
                "Если вы не регистрировались в Convioo — просто "
                "проигнорируйте это письмо."
            ),
            uk=(
                "Якщо ви не реєструвалися в Convioo — просто "
                "проігноруйте цей лист."
            ),
            en="If you didn't sign up for Convioo, just ignore this email.",
        )
        + "</p>"
    )
    return (
        _wrap_html(heading=_greeting(_esc(name), lang), body_html=body),
        text,
    )


def render_password_reset_email(
    *, name: str, reset_url: str, lang: str | None = None
) -> tuple[str, str]:
    """Email a user clicked 'Forgot password' on their account."""
    lang = normalize_lang(lang)
    text = pick(
        lang,
        ru=(
            f"Привет, {name}!\n\n"
            "Кто-то (надеемся, вы) запросил сброс пароля для аккаунта Convioo. "
            f"Чтобы задать новый пароль, перейдите по ссылке:\n{reset_url}\n\n"
            "Ссылка действует 1 час. Если это были не вы — просто "
            "проигнорируйте письмо, ваш пароль не изменится.\n\n"
            "— Команда Convioo"
        ),
        uk=(
            f"Привіт, {name}!\n\n"
            "Хтось (сподіваємось, ви) запросив скидання пароля для акаунта Convioo. "
            f"Щоб задати новий пароль, перейдіть за посиланням:\n{reset_url}\n\n"
            "Посилання дійсне 1 годину. Якщо це були не ви — просто "
            "проігноруйте лист, ваш пароль не зміниться.\n\n"
            "— Команда Convioo"
        ),
        en=(
            f"Hi {name}!\n\n"
            "Someone (hopefully you) requested a password reset for your "
            f"Convioo account. To set a new password, follow this link:\n{reset_url}\n\n"
            "The link is valid for 1 hour. If it wasn't you, just ignore "
            "this email — your password won't change.\n\n"
            "— The Convioo team"
        ),
    )
    body = (
        '<p style="color:#475569; line-height:1.55; font-size:14.5px;">'
        + pick(
            lang,
            ru=(
                "Кто-то (надеемся, вы) запросил сброс пароля для вашего "
                "аккаунта Convioo. Чтобы задать новый пароль, нажмите "
                "кнопку ниже. Ссылка действует 1&nbsp;час."
            ),
            uk=(
                "Хтось (сподіваємось, ви) запросив скидання пароля для "
                "вашого акаунта Convioo. Щоб задати новий пароль, "
                "натисніть кнопку нижче. Посилання дійсне 1&nbsp;годину."
            ),
            en=(
                "Someone (hopefully you) requested a password reset for "
                "your Convioo account. To set a new password, click the "
                "button below. The link is valid for 1&nbsp;hour."
            ),
        )
        + "</p>"
        + _button_html(
            href=reset_url,
            label=pick(
                lang,
                ru="Сбросить пароль",
                uk="Скинути пароль",
                en="Reset password",
            ),
            lang=lang,
        )
        + '<p style="font-size:12px; color:#94a3b8; margin-top:24px;">'
        + pick(
            lang,
            ru=(
                "Если это были не вы — просто проигнорируйте письмо. Ваш "
                "пароль не изменится."
            ),
            uk=(
                "Якщо це були не ви — просто проігноруйте лист. Ваш "
                "пароль не зміниться."
            ),
            en=(
                "If it wasn't you, just ignore this email. Your password "
                "won't change."
            ),
        )
        + "</p>"
    )
    return (
        _wrap_html(heading=_greeting(_esc(name), lang), body_html=body),
        text,
    )


def render_password_changed_email(
    *,
    name: str,
    ip: str | None,
    user_agent: str | None,
    when_iso: str,
    lang: str | None = None,
) -> tuple[str, str]:
    """Security alert — sent right after a successful password change."""
    lang = normalize_lang(lang)
    unknown = pick(lang, ru="неизвестно", uk="невідомо", en="unknown")
    where = ip or unknown
    ua = user_agent or unknown
    when_label = pick(lang, ru="Когда", uk="Коли", en="When")
    device_label = pick(lang, ru="Устройство", uk="Пристрій", en="Device")
    text = pick(
        lang,
        ru=(
            f"Привет, {name}!\n\n"
            "Пароль вашего аккаунта Convioo только что был изменён.\n"
            f"Когда: {when_iso}\nIP: {where}\nУстройство: {ua}\n\n"
            "Если это были вы — всё в порядке, можно ничего не делать. "
            "Если нет — немедленно сбросьте пароль через 'Забыли пароль?' "
            "и напишите нам на [email protected].\n\n"
            "— Команда Convioo"
        ),
        uk=(
            f"Привіт, {name}!\n\n"
            "Пароль вашого акаунта Convioo щойно було змінено.\n"
            f"Коли: {when_iso}\nIP: {where}\nПристрій: {ua}\n\n"
            "Якщо це були ви — все гаразд, нічого робити не треба. "
            "Якщо ні — негайно скиньте пароль через «Забули пароль?» "
            "і напишіть нам на [email protected].\n\n"
            "— Команда Convioo"
        ),
        en=(
            f"Hi {name}!\n\n"
            "The password for your Convioo account has just been changed.\n"
            f"When: {when_iso}\nIP: {where}\nDevice: {ua}\n\n"
            "If this was you, everything is fine — no action needed. "
            "If not, reset your password immediately via 'Forgot "
            "password?' and email us at [email protected].\n\n"
            "— The Convioo team"
        ),
    )
    body = (
        '<p style="color:#475569; line-height:1.55; font-size:14.5px;">'
        + pick(
            lang,
            ru="Пароль вашего аккаунта Convioo только что был изменён.",
            uk="Пароль вашого акаунта Convioo щойно було змінено.",
            en="The password for your Convioo account has just been changed.",
        )
        + "</p>"
        '<ul style="color:#475569; font-size:14px; line-height:1.7;">'
        f"<li>{when_label}: {when_iso}</li><li>IP: {where}</li>"
        f"<li>{device_label}: {ua}</li></ul>"
        '<p style="color:#475569; line-height:1.55; font-size:14.5px;">'
        + pick(
            lang,
            ru=(
                "Если это были не вы — немедленно используйте «Забыли "
                "пароль?» и напишите нам на [email protected]."
            ),
            uk=(
                "Якщо це були не ви — негайно скористайтеся «Забули "
                "пароль?» і напишіть нам на [email protected]."
            ),
            en=(
                "If this wasn't you, use 'Forgot password?' immediately "
                "and email us at [email protected]."
            ),
        )
        + "</p>"
    )
    heading = pick(
        lang, ru="Пароль изменён", uk="Пароль змінено", en="Password changed"
    )
    return _wrap_html(heading=heading, body_html=body), text


def render_email_recovery_email(
    *,
    name: str,
    account_email_masked: str,
    change_url: str,
    lang: str | None = None,
) -> tuple[str, str]:
    """Reminder of which email the account is registered under."""
    lang = normalize_lang(lang)
    text = pick(
        lang,
        ru=(
            f"Привет, {name}!\n\n"
            "Вы запросили напоминание о email от аккаунта Convioo.\n"
            f"Аккаунт зарегистрирован на: {account_email_masked}\n\n"
            "Если хотите сменить email на этот резервный — перейдите по "
            f"ссылке:\n{change_url}\n\n"
            "Ссылка действует 1 час. Если это были не вы — игнорируйте "
            "письмо.\n\n"
            "— Команда Convioo"
        ),
        uk=(
            f"Привіт, {name}!\n\n"
            "Ви запросили нагадування про email акаунта Convioo.\n"
            f"Акаунт зареєстровано на: {account_email_masked}\n\n"
            "Якщо хочете змінити email на цей резервний — перейдіть за "
            f"посиланням:\n{change_url}\n\n"
            "Посилання дійсне 1 годину. Якщо це були не ви — ігноруйте "
            "лист.\n\n"
            "— Команда Convioo"
        ),
        en=(
            f"Hi {name}!\n\n"
            "You requested a reminder of the email on your Convioo "
            "account.\n"
            f"The account is registered to: {account_email_masked}\n\n"
            "If you want to switch the account email to this recovery "
            f"address, follow this link:\n{change_url}\n\n"
            "The link is valid for 1 hour. If it wasn't you, ignore "
            "this email.\n\n"
            "— The Convioo team"
        ),
    )
    body = (
        '<p style="color:#475569; line-height:1.55; font-size:14.5px;">'
        + pick(
            lang,
            ru=(
                "Вы запросили напоминание о email от аккаунта Convioo. "
                "Аккаунт зарегистрирован на:"
            ),
            uk=(
                "Ви запросили нагадування про email акаунта Convioo. "
                "Акаунт зареєстровано на:"
            ),
            en=(
                "You requested a reminder of the email on your Convioo "
                "account. The account is registered to:"
            ),
        )
        + '</p><p style="font-weight:600; '
        f'color:#1F3D5C; font-size:16px;">{account_email_masked}</p>'
        '<p style="color:#475569; line-height:1.55; font-size:14.5px;">'
        + pick(
            lang,
            ru=(
                "Если хотите сменить email аккаунта на этот резервный, "
                "нажмите кнопку ниже. Ссылка действует 1&nbsp;час."
            ),
            uk=(
                "Якщо хочете змінити email акаунта на цей резервний, "
                "натисніть кнопку нижче. Посилання дійсне 1&nbsp;годину."
            ),
            en=(
                "If you want to switch the account email to this "
                "recovery address, click the button below. The link is "
                "valid for 1&nbsp;hour."
            ),
        )
        + "</p>"
        + _button_html(
            href=change_url,
            label=pick(
                lang,
                ru="Сменить email на этот",
                uk="Змінити email на цей",
                en="Switch to this email",
            ),
            lang=lang,
        )
        + '<p style="font-size:12px; color:#94a3b8; margin-top:24px;">'
        + pick(
            lang,
            ru="Если это были не вы — просто проигнорируйте письмо.",
            uk="Якщо це були не ви — просто проігноруйте лист.",
            en="If it wasn't you, just ignore this email.",
        )
        + "</p>"
    )
    return (
        _wrap_html(heading=_greeting(_esc(name), lang), body_html=body),
        text,
    )


def render_email_changed_alert(
    *,
    name: str,
    new_email_masked: str,
    when_iso: str,
    lang: str | None = None,
) -> tuple[str, str]:
    """Sent to the OLD address after the user changed their primary email."""
    lang = normalize_lang(lang)
    text = pick(
        lang,
        ru=(
            f"Привет, {name}!\n\n"
            f"Email вашего аккаунта Convioo был изменён на: {new_email_masked}.\n"
            f"Когда: {when_iso}\n\n"
            "Если это были не вы — немедленно напишите нам на "
            "[email protected], мы вернём аккаунт.\n\n"
            "— Команда Convioo"
        ),
        uk=(
            f"Привіт, {name}!\n\n"
            f"Email вашого акаунта Convioo було змінено на: {new_email_masked}.\n"
            f"Коли: {when_iso}\n\n"
            "Якщо це були не ви — негайно напишіть нам на "
            "[email protected], ми повернемо акаунт.\n\n"
            "— Команда Convioo"
        ),
        en=(
            f"Hi {name}!\n\n"
            f"The email on your Convioo account was changed to: {new_email_masked}.\n"
            f"When: {when_iso}\n\n"
            "If this wasn't you, email us immediately at "
            "[email protected] and we'll recover the account.\n\n"
            "— The Convioo team"
        ),
    )
    new_email_label = pick(
        lang, ru="Новый email", uk="Новий email", en="New email"
    )
    when_label = pick(lang, ru="Когда", uk="Коли", en="When")
    body = (
        '<p style="color:#475569; line-height:1.55; font-size:14.5px;">'
        + pick(
            lang,
            ru="Email вашего аккаунта Convioo был изменён.",
            uk="Email вашого акаунта Convioo було змінено.",
            en="The email on your Convioo account was changed.",
        )
        + "</p>"
        '<ul style="color:#475569; font-size:14px; line-height:1.7;">'
        f"<li>{new_email_label}: {new_email_masked}</li>"
        f"<li>{when_label}: {when_iso}</li></ul>"
        '<p style="color:#475569; line-height:1.55; font-size:14.5px;">'
        + pick(
            lang,
            ru=(
                "Если это были не вы — немедленно напишите нам на "
                "[email protected], мы поможем вернуть аккаунт."
            ),
            uk=(
                "Якщо це були не ви — негайно напишіть нам на "
                "[email protected], ми допоможемо повернути акаунт."
            ),
            en=(
                "If this wasn't you, email us immediately at "
                "[email protected] and we'll help recover the account."
            ),
        )
        + "</p>"
    )
    heading = pick(
        lang, ru="Email изменён", uk="Email змінено", en="Email changed"
    )
    return _wrap_html(heading=heading, body_html=body), text


def render_new_device_login_email(
    *,
    name: str,
    ip: str | None,
    user_agent: str | None,
    when_iso: str,
    lang: str | None = None,
) -> tuple[str, str]:
    lang = normalize_lang(lang)
    unknown = pick(lang, ru="неизвестно", uk="невідомо", en="unknown")
    where = ip or unknown
    ua = user_agent or unknown
    when_label = pick(lang, ru="Когда", uk="Коли", en="When")
    device_label = pick(lang, ru="Устройство", uk="Пристрій", en="Device")
    text = pick(
        lang,
        ru=(
            f"Привет, {name}!\n\n"
            "В ваш аккаунт Convioo только что вошли с нового устройства.\n"
            f"Когда: {when_iso}\nIP: {where}\nУстройство: {ua}\n\n"
            "Если это были вы — игнорируйте письмо. Если нет — смените "
            "пароль и завершите все сессии в Настройках → Безопасность.\n\n"
            "— Команда Convioo"
        ),
        uk=(
            f"Привіт, {name}!\n\n"
            "У ваш акаунт Convioo щойно увійшли з нового пристрою.\n"
            f"Коли: {when_iso}\nIP: {where}\nПристрій: {ua}\n\n"
            "Якщо це були ви — ігноруйте лист. Якщо ні — змініть "
            "пароль і завершіть усі сесії в Налаштуваннях → Безпека.\n\n"
            "— Команда Convioo"
        ),
        en=(
            f"Hi {name}!\n\n"
            "Your Convioo account was just signed into from a new device.\n"
            f"When: {when_iso}\nIP: {where}\nDevice: {ua}\n\n"
            "If this was you, ignore this email. If not, change your "
            "password and end all sessions in Settings → Security.\n\n"
            "— The Convioo team"
        ),
    )
    body = (
        '<p style="color:#475569; line-height:1.55; font-size:14.5px;">'
        + pick(
            lang,
            ru="В ваш аккаунт Convioo только что вошли с нового устройства.",
            uk="У ваш акаунт Convioo щойно увійшли з нового пристрою.",
            en="Your Convioo account was just signed into from a new device.",
        )
        + "</p>"
        '<ul style="color:#475569; font-size:14px; line-height:1.7;">'
        f"<li>{when_label}: {when_iso}</li><li>IP: {where}</li>"
        f"<li>{device_label}: {ua}</li></ul>"
        '<p style="color:#475569; line-height:1.55; font-size:14.5px;">'
        + pick(
            lang,
            ru=(
                "Если это были не вы — смените пароль и завершите все "
                "сессии в Настройках → Безопасность."
            ),
            uk=(
                "Якщо це були не ви — змініть пароль і завершіть усі "
                "сесії в Налаштуваннях → Безпека."
            ),
            en=(
                "If this wasn't you, change your password and end all "
                "sessions in Settings → Security."
            ),
        )
        + "</p>"
    )
    heading = pick(
        lang,
        ru="Вход с нового устройства",
        uk="Вхід з нового пристрою",
        en="New device sign-in",
    )
    return _wrap_html(heading=heading, body_html=body), text


def render_account_locked_email(
    *, name: str, unlock_iso: str, lang: str | None = None
) -> tuple[str, str]:
    lang = normalize_lang(lang)
    text = pick(
        lang,
        ru=(
            f"Привет, {name}!\n\n"
            "Мы временно заблокировали входы в ваш аккаунт Convioo "
            "после серии неудачных попыток.\n"
            f"Разблокировка: {unlock_iso}\n\n"
            "Если это были не вы — рекомендуем сбросить пароль через "
            "«Забыли пароль?» прямо сейчас.\n\n"
            "— Команда Convioo"
        ),
        uk=(
            f"Привіт, {name}!\n\n"
            "Ми тимчасово заблокували входи у ваш акаунт Convioo "
            "після серії невдалих спроб.\n"
            f"Розблокування: {unlock_iso}\n\n"
            "Якщо це були не ви — радимо скинути пароль через "
            "«Забули пароль?» просто зараз.\n\n"
            "— Команда Convioo"
        ),
        en=(
            f"Hi {name}!\n\n"
            "We've temporarily locked sign-ins to your Convioo account "
            "after a series of failed attempts.\n"
            f"Unlocks at: {unlock_iso}\n\n"
            "If this wasn't you, we recommend resetting your password "
            "via 'Forgot password?' right now.\n\n"
            "— The Convioo team"
        ),
    )
    body = (
        '<p style="color:#475569; line-height:1.55; font-size:14.5px;">'
        + pick(
            lang,
            ru=(
                "Мы временно заблокировали входы в ваш аккаунт Convioo "
                "после серии неудачных попыток подбора пароля."
            ),
            uk=(
                "Ми тимчасово заблокували входи у ваш акаунт Convioo "
                "після серії невдалих спроб підбору пароля."
            ),
            en=(
                "We've temporarily locked sign-ins to your Convioo "
                "account after a series of failed password attempts."
            ),
        )
        + "</p>"
        '<p style="color:#475569; font-size:14.5px;">'
        + pick(
            lang,
            ru=f"Разблокировка автоматически: <b>{unlock_iso}</b>.",
            uk=f"Розблокування автоматично: <b>{unlock_iso}</b>.",
            en=f"Unlocks automatically at: <b>{unlock_iso}</b>.",
        )
        + "</p>"
        '<p style="color:#475569; line-height:1.55; font-size:14.5px;">'
        + pick(
            lang,
            ru=(
                "Если это были не вы — рекомендуем сбросить пароль через "
                "«Забыли пароль?» прямо сейчас, чтобы перекрыть атаку."
            ),
            uk=(
                "Якщо це були не ви — радимо скинути пароль через "
                "«Забули пароль?» просто зараз, щоб зупинити атаку."
            ),
            en=(
                "If this wasn't you, we recommend resetting your "
                "password via 'Forgot password?' right now to cut off "
                "the attack."
            ),
        )
        + "</p>"
    )
    heading = pick(
        lang,
        ru="Аккаунт временно заблокирован",
        uk="Акаунт тимчасово заблоковано",
        en="Account temporarily locked",
    )
    return _wrap_html(heading=heading, body_html=body), text


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
