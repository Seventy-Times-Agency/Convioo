"""Persistence + lifecycle for OAuth tokens stored encrypted at rest.

Wraps the Fernet vault and the Gmail refresh-helper so the route
handlers stay short. Every call goes through ``ensure_fresh_token``
which transparently rotates an expired access token using the saved
refresh token — the handler always gets a usable bearer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.config import get_settings
from leadgen.core.services.secrets_vault import decrypt, encrypt
from leadgen.db.models import OAuthCredential
from leadgen.integrations.gmail import (
    GmailError,
    TokenSet,
    refresh_access_token,
)

logger = logging.getLogger(__name__)

# Treat tokens within this window of expiry as already expired so we
# refresh proactively instead of letting an in-flight send race the
# expiry boundary and 401.
EXPIRY_GRACE = timedelta(seconds=60)


class OAuthStoreError(RuntimeError):
    """Raised on missing credential / refresh failure."""


@dataclass(slots=True)
class FreshAccessToken:
    """Bearer good for at least ``EXPIRY_GRACE`` more seconds."""

    access_token: str
    expires_at: datetime
    account_email: str | None


async def get_credential(
    session: AsyncSession, *, user_id: int, provider: str
) -> OAuthCredential | None:
    return (
        await session.execute(
            select(OAuthCredential)
            .where(OAuthCredential.user_id == user_id)
            .where(OAuthCredential.provider == provider)
        )
    ).scalar_one_or_none()


async def save_tokens(
    session: AsyncSession,
    *,
    user_id: int,
    provider: str,
    tokens: TokenSet,
    account_email: str | None,
) -> OAuthCredential:
    """Insert-or-update the ``oauth_credentials`` row for this user.

    Google issues the refresh token only on the very first consent
    (and on any consent flow with ``prompt=consent``); when a refresh
    call returns no new refresh token we keep the existing one.
    """
    existing = await get_credential(
        session, user_id=user_id, provider=provider
    )
    access_ct = encrypt(tokens.access_token)
    refresh_ct = (
        encrypt(tokens.refresh_token) if tokens.refresh_token else None
    )
    now = datetime.now(timezone.utc)
    if existing is None:
        row = OAuthCredential(
            user_id=user_id,
            provider=provider,
            access_token_ciphertext=access_ct,
            refresh_token_ciphertext=refresh_ct,
            expires_at=tokens.expires_at,
            scope=tokens.scope,
            account_email=account_email,
        )
        session.add(row)
    else:
        existing.access_token_ciphertext = access_ct
        if refresh_ct is not None:
            existing.refresh_token_ciphertext = refresh_ct
        existing.expires_at = tokens.expires_at
        if tokens.scope is not None:
            existing.scope = tokens.scope
        if account_email is not None:
            existing.account_email = account_email
        existing.updated_at = now
        row = existing
    await session.commit()
    await session.refresh(row)
    return row


async def ensure_fresh_token(
    session: AsyncSession,
    *,
    user_id: int,
    provider: str,
    now: datetime | None = None,
) -> FreshAccessToken:
    """Return a non-expired access token, refreshing on the fly if needed."""
    moment = now or datetime.now(timezone.utc)
    cred = await get_credential(
        session, user_id=user_id, provider=provider
    )
    if cred is None:
        raise OAuthStoreError(
            f"no {provider} credentials connected for user {user_id}"
        )

    expires_at = cred.expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    needs_refresh = (
        expires_at is None or expires_at - EXPIRY_GRACE <= moment
    )

    if not needs_refresh:
        return FreshAccessToken(
            access_token=decrypt(cred.access_token_ciphertext),
            expires_at=expires_at,
            account_email=cred.account_email,
        )

    if not cred.refresh_token_ciphertext:
        raise OAuthStoreError(
            "access token expired and no refresh token is on file — "
            "ask the user to reconnect"
        )

    settings = get_settings()
    if provider == "gmail":
        client_id = settings.google_oauth_client_id
        client_secret = settings.google_oauth_client_secret
    else:
        raise OAuthStoreError(f"unknown oauth provider: {provider}")

    try:
        new_tokens = await refresh_access_token(
            decrypt(cred.refresh_token_ciphertext),
            client_id=client_id,
            client_secret=client_secret,
        )
    except GmailError as exc:
        raise OAuthStoreError(f"refresh failed: {exc}") from exc

    cred.access_token_ciphertext = encrypt(new_tokens.access_token)
    cred.expires_at = new_tokens.expires_at
    if new_tokens.scope is not None:
        cred.scope = new_tokens.scope
    cred.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(cred)
    return FreshAccessToken(
        access_token=new_tokens.access_token,
        expires_at=new_tokens.expires_at,
        account_email=cred.account_email,
    )
