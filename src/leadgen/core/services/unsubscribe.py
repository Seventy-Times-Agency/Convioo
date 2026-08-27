"""One-click unsubscribe: signed tokens, headers, and email footer.

A recipient-facing unsubscribe link is embedded in every cold-outreach
email (footer) plus the RFC 8058 ``List-Unsubscribe`` / one-click
headers. Clicking (or the mailbox's one-click POST) adds the recipient to
the sender's suppression list, so they are never contacted again. Pairs
with :mod:`leadgen.core.services.suppression`.

The token is self-contained and HMAC-signed with ``AUTH_JWT_SECRET`` — no
DB lookup needed to render a link, and it can't be forged to unsubscribe
someone from another sender's list.
"""

from __future__ import annotations

import base64
import hashlib
import hmac

from leadgen.config import get_settings


def _sign(payload_b64: str) -> str:
    key = get_settings().auth_jwt_secret.encode()
    sig = hmac.new(key, payload_b64.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode().rstrip("=")[:32]


def make_unsubscribe_token(user_id: int, email: str) -> str:
    """Signed ``<b64(user_id:email)>.<sig>`` token for an unsubscribe link."""
    payload = f"{user_id}:{email.strip().lower()}"
    payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    return f"{payload_b64}.{_sign(payload_b64)}"


def parse_unsubscribe_token(token: str) -> tuple[int, str] | None:
    """Return ``(user_id, email)`` if the token is well-formed and signed."""
    try:
        payload_b64, sig = token.split(".", 1)
    except ValueError:
        return None
    if not hmac.compare_digest(sig, _sign(payload_b64)):
        return None
    try:
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        raw = base64.urlsafe_b64decode(padded).decode()
        user_id_str, email = raw.split(":", 1)
        return int(user_id_str), email
    except (ValueError, UnicodeDecodeError):
        return None


def unsubscribe_url(user_id: int, email: str) -> str:
    base = get_settings().public_app_url.rstrip("/")
    return f"{base}/api/v1/unsubscribe/{make_unsubscribe_token(user_id, email)}"


def list_unsubscribe_headers(url: str) -> dict[str, str]:
    """RFC 2369 + RFC 8058 one-click headers for a cold-outreach message."""
    return {
        "List-Unsubscribe": f"<{url}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }


def _postal_address() -> str:
    # Optional per-deploy sender postal address (CAN-SPAM). Included in the
    # footer only when configured; never blocks a send when absent.
    return (getattr(get_settings(), "sender_postal_address", "") or "").strip()


def unsubscribe_footer_html(url: str) -> str:
    postal = _postal_address()
    postal_html = (
        f'<div style="margin-top:4px">{postal}</div>' if postal else ""
    )
    return (
        '<div style="margin-top:24px;padding-top:12px;border-top:1px solid #eee;'
        'font-size:12px;color:#888">'
        f'<a href="{url}" style="color:#888">Unsubscribe</a>'
        f"{postal_html}"
        "</div>"
    )


def unsubscribe_footer_text(url: str) -> str:
    postal = _postal_address()
    tail = f"\n{postal}" if postal else ""
    return f"\n\n---\nUnsubscribe: {url}{tail}"
