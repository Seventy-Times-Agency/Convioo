"""Google OAuth + Gmail send for user-owned outreach.

This module is intentionally framework-agnostic: it speaks to Google
over plain ``httpx`` and persists tokens through a SQLAlchemy session
the caller provides. The web adapter wraps it with HTTP routes; a
future Telegram or CLI surface could reuse the same primitives.

Design notes
------------
* Tokens at rest can be encrypted with Fernet when
  ``GOOGLE_OAUTH_TOKEN_KEY`` is set. Without a key (local dev) tokens
  are stored in plaintext and ``token_encrypted`` stays False so a
  later key-rollout can re-encrypt them in place.
* ``redirect_uri`` is derived from ``PUBLIC_API_URL`` if set,
  otherwise from the request host. The same URI must be registered in
  the Google Cloud Console OAuth client.
* Required scopes: ``gmail.send`` (the only Gmail scope we need —
  send-only, no inbox read), plus ``userinfo.email`` /
  ``userinfo.profile`` so we can show the user *which* address they
  connected.
"""

from __future__ import annotations

import base64
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.config import get_settings
from leadgen.db.models import UserEmailAccount

logger = logging.getLogger(__name__)


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 (URL, not creds)
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GMAIL_SEND_URL = (
    "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
)
GMAIL_SCOPES = (
    "https://www.googleapis.com/auth/gmail.send "
    "https://www.googleapis.com/auth/userinfo.email "
    "https://www.googleapis.com/auth/userinfo.profile"
)
# 5-minute refresh skew so we don't hand out a token that expires mid-flight.
REFRESH_SKEW = timedelta(minutes=5)


class GoogleOAuthError(RuntimeError):
    """Raised when the OAuth flow fails (provider error, missing config)."""


class GoogleNotConfiguredError(GoogleOAuthError):
    """Raised when GOOGLE_OAUTH_CLIENT_ID/SECRET are not set."""


class GmailSendError(RuntimeError):
    """Raised when Gmail returns a non-2xx for the send call."""


@dataclass(slots=True, frozen=True)
class ConnectedAccount:
    """SPA-facing summary of a connected mailbox."""

    id: str
    provider: str
    email: str
    display_name: str | None
    connected_at: datetime
    revoked: bool


def _fernet() -> Fernet | None:
    key = get_settings().google_oauth_token_key.strip()
    if not key:
        return None
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, TypeError):
        logger.error("GOOGLE_OAUTH_TOKEN_KEY is not a valid Fernet key")
        return None


def _encrypt(value: str | None) -> tuple[str | None, bool]:
    """Return ``(stored_value, encrypted_flag)``.

    Falls back to plaintext when no key is configured.
    """
    if value is None:
        return None, False
    f = _fernet()
    if f is None:
        return value, False
    return f.encrypt(value.encode("utf-8")).decode("ascii"), True


def _decrypt(value: str | None, *, encrypted: bool) -> str | None:
    if value is None or not encrypted:
        return value
    f = _fernet()
    if f is None:
        logger.error("token_encrypted=true but GOOGLE_OAUTH_TOKEN_KEY missing")
        return None
    try:
        return f.decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken:
        logger.exception("failed to decrypt OAuth token")
        return None


def is_configured() -> bool:
    s = get_settings()
    return bool(s.google_oauth_client_id and s.google_oauth_client_secret)


def build_authorize_url(*, redirect_uri: str, state: str) -> str:
    """Compose the consent URL the user is bounced to."""
    s = get_settings()
    if not is_configured():
        raise GoogleNotConfiguredError(
            "GOOGLE_OAUTH_CLIENT_ID/SECRET are not set on the server"
        )
    params = {
        "client_id": s.google_oauth_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GMAIL_SCOPES,
        "access_type": "offline",
        "include_granted_scopes": "true",
        # Forcing consent guarantees we get a refresh_token even if the
        # user previously connected and then disconnected.
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def make_state_token() -> str:
    """Random token bound to the OAuth round-trip (CSRF defence)."""
    return secrets.token_urlsafe(24)


async def exchange_code_for_tokens(
    *, code: str, redirect_uri: str
) -> dict[str, Any]:
    s = get_settings()
    if not is_configured():
        raise GoogleNotConfiguredError("OAuth client credentials missing")
    payload = {
        "code": code,
        "client_id": s.google_oauth_client_id,
        "client_secret": s.google_oauth_client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(GOOGLE_TOKEN_URL, data=payload)
    if response.status_code >= 400:
        logger.error(
            "google token exchange failed: %s %s",
            response.status_code,
            response.text[:512],
        )
        raise GoogleOAuthError(
            f"token exchange returned {response.status_code}"
        )
    return response.json()


async def fetch_userinfo(*, access_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if response.status_code >= 400:
        raise GoogleOAuthError(
            f"userinfo returned {response.status_code}: {response.text[:200]}"
        )
    return response.json()


async def upsert_account(
    session: AsyncSession,
    *,
    user_id: int,
    email: str,
    display_name: str | None,
    access_token: str,
    refresh_token: str | None,
    expires_in: int,
    scopes: str,
) -> UserEmailAccount:
    """Insert or update the row for this (user_id, "google", email)."""
    existing = (
        await session.execute(
            select(UserEmailAccount)
            .where(UserEmailAccount.user_id == user_id)
            .where(UserEmailAccount.provider == "google")
            .where(UserEmailAccount.email == email)
            .limit(1)
        )
    ).scalar_one_or_none()

    enc_access, enc1 = _encrypt(access_token)
    enc_refresh, enc2 = _encrypt(refresh_token)
    encrypted = enc1 or enc2
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    now = datetime.now(timezone.utc)

    if existing is None:
        row = UserEmailAccount(
            user_id=user_id,
            provider="google",
            email=email,
            display_name=display_name,
            scopes=scopes,
            access_token=enc_access,
            refresh_token=enc_refresh,
            token_expires_at=expires_at,
            token_encrypted=encrypted,
        )
        session.add(row)
        await session.flush()
        return row
    existing.display_name = display_name or existing.display_name
    existing.scopes = scopes
    existing.access_token = enc_access
    # Google sometimes omits refresh_token on re-consent if the user
    # already granted offline access. Keep the previous one in that case.
    if enc_refresh is not None:
        existing.refresh_token = enc_refresh
    existing.token_expires_at = expires_at
    existing.token_encrypted = encrypted
    existing.revoked_at = None
    existing.updated_at = now
    await session.flush()
    return existing


async def list_accounts(
    session: AsyncSession, *, user_id: int
) -> list[ConnectedAccount]:
    rows = (
        await session.execute(
            select(UserEmailAccount)
            .where(UserEmailAccount.user_id == user_id)
            .where(UserEmailAccount.provider == "google")
            .order_by(UserEmailAccount.created_at.desc())
        )
    ).scalars().all()
    return [
        ConnectedAccount(
            id=str(r.id),
            provider=r.provider,
            email=r.email,
            display_name=r.display_name,
            connected_at=r.created_at,
            revoked=r.revoked_at is not None,
        )
        for r in rows
    ]


async def revoke_account(
    session: AsyncSession, *, user_id: int, account_id: str
) -> bool:
    """Mark the account revoked locally and best-effort revoke at Google."""
    row = (
        await session.execute(
            select(UserEmailAccount)
            .where(UserEmailAccount.user_id == user_id)
            .where(UserEmailAccount.id == account_id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    refresh = _decrypt(row.refresh_token, encrypted=row.token_encrypted)
    row.revoked_at = datetime.now(timezone.utc)
    row.access_token = None
    row.refresh_token = None
    row.token_expires_at = None
    row.token_encrypted = False
    if refresh:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                await client.post(
                    "https://oauth2.googleapis.com/revoke",
                    data={"token": refresh},
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded"
                    },
                )
        except Exception:  # noqa: BLE001
            logger.warning(
                "google token revocation request failed", exc_info=True
            )
    return True


async def _get_valid_access_token(
    session: AsyncSession, row: UserEmailAccount
) -> str:
    """Refresh if needed, return a usable access token."""
    if row.revoked_at is not None:
        raise GmailSendError("mailbox connection has been revoked")
    access = _decrypt(row.access_token, encrypted=row.token_encrypted)
    refresh = _decrypt(row.refresh_token, encrypted=row.token_encrypted)
    expires_at = row.token_expires_at
    needs_refresh = (
        access is None
        or expires_at is None
        or expires_at - REFRESH_SKEW <= datetime.now(timezone.utc)
    )
    if not needs_refresh and access is not None:
        return access
    if not refresh:
        raise GmailSendError(
            "access token expired and no refresh token on file — reconnect Gmail"
        )
    s = get_settings()
    payload = {
        "client_id": s.google_oauth_client_id,
        "client_secret": s.google_oauth_client_secret,
        "refresh_token": refresh,
        "grant_type": "refresh_token",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(GOOGLE_TOKEN_URL, data=payload)
    if response.status_code >= 400:
        logger.error(
            "google token refresh failed: %s %s",
            response.status_code,
            response.text[:512],
        )
        raise GmailSendError(
            f"token refresh returned {response.status_code}"
        )
    data = response.json()
    new_access = data["access_token"]
    expires_in = int(data.get("expires_in", 3600))
    enc_access, encrypted = _encrypt(new_access)
    row.access_token = enc_access
    row.token_expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=expires_in
    )
    row.token_encrypted = encrypted or row.token_encrypted
    row.updated_at = datetime.now(timezone.utc)
    await session.flush()
    return new_access


def _build_mime(
    *, sender: str, sender_name: str | None, to: str, subject: str, body: str
) -> str:
    msg = EmailMessage()
    msg["To"] = to
    if sender_name:
        msg["From"] = f"{sender_name} <{sender}>"
    else:
        msg["From"] = sender
    msg["Subject"] = subject
    msg.set_content(body)
    raw = msg.as_bytes()
    return base64.urlsafe_b64encode(raw).decode("ascii")


@dataclass(slots=True, frozen=True)
class GmailSendResult:
    message_id: str
    thread_id: str | None


async def send_via_gmail(
    session: AsyncSession,
    *,
    user_id: int,
    account_id: str | None,
    to: str,
    subject: str,
    body: str,
) -> GmailSendResult:
    """Send an email through the user's connected Gmail account.

    When ``account_id`` is None, picks the most-recently-connected
    non-revoked account for that user. Raises ``GmailSendError`` when
    no account is connected, the connection was revoked, or Gmail
    rejects the send.
    """
    query = (
        select(UserEmailAccount)
        .where(UserEmailAccount.user_id == user_id)
        .where(UserEmailAccount.provider == "google")
        .where(UserEmailAccount.revoked_at.is_(None))
    )
    if account_id:
        query = query.where(UserEmailAccount.id == account_id)
    query = query.order_by(UserEmailAccount.created_at.desc()).limit(1)
    row = (await session.execute(query)).scalar_one_or_none()
    if row is None:
        raise GmailSendError(
            "no connected Gmail mailbox for this user — connect one in Settings"
        )

    access_token = await _get_valid_access_token(session, row)
    raw = _build_mime(
        sender=row.email,
        sender_name=row.display_name,
        to=to,
        subject=subject,
        body=body,
    )
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            GMAIL_SEND_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={"raw": raw},
        )
    if response.status_code >= 400:
        logger.error(
            "gmail send failed for user=%s status=%s body=%s",
            user_id,
            response.status_code,
            response.text[:512],
        )
        raise GmailSendError(
            f"Gmail returned {response.status_code}: {response.text[:200]}"
        )
    data = response.json()
    return GmailSendResult(
        message_id=str(data.get("id", "")),
        thread_id=(str(data["threadId"]) if data.get("threadId") else None),
    )
