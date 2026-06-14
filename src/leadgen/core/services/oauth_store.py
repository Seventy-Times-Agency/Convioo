"""Persistence + lifecycle for OAuth tokens stored encrypted at rest.

Wraps the Fernet vault and the Gmail refresh-helper so the route
handlers stay short. Every call goes through ``ensure_fresh_token``
which transparently rotates an expired access token using the saved
refresh token — the handler always gets a usable bearer.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.config import get_settings
from leadgen.core.services.secrets_vault import decrypt, encrypt
from leadgen.db.models import OAuthCredential
from leadgen.integrations.gmail import (
    GmailError,
    TokenSet,
    refresh_access_token,
)
from leadgen.integrations.hubspot import (
    HubspotError,
    HubspotTokenSet,
)
from leadgen.integrations.hubspot import (
    refresh_access_token as refresh_hubspot_token,
)
from leadgen.integrations.outlook import (
    OutlookError,
)
from leadgen.integrations.outlook import (
    TokenSet as OutlookTokenSet,
)
from leadgen.integrations.outlook import (
    refresh_access_token as refresh_outlook_token,
)
from leadgen.integrations.pipedrive import (
    PipedriveError,
    PipedriveTokenSet,
)
from leadgen.integrations.pipedrive import (
    refresh_access_token as refresh_pipedrive_token,
)

logger = logging.getLogger(__name__)

# Treat tokens within this window of expiry as already expired so we
# refresh proactively instead of letting an in-flight send race the
# expiry boundary and 401.
EXPIRY_GRACE = timedelta(seconds=60)


def _advisory_lock_key(user_id: int, provider: str) -> int:
    """Stable signed 64-bit int identifying a (user, provider) refresh.

    ``pg_advisory_xact_lock`` takes a bigint. We hash ``user_id:provider``
    with blake2b and fold the leading 8 bytes into the signed bigint range
    so the same pair always maps to the same lock and collisions across
    unrelated pairs are vanishingly unlikely.
    """
    digest = hashlib.blake2b(
        f"{user_id}:{provider}".encode(), digest_size=8
    ).digest()
    unsigned = int.from_bytes(digest, "big", signed=False)
    # Map [0, 2**64) into the signed bigint range [-2**63, 2**63).
    return unsigned - (1 << 63)


async def _acquire_refresh_lock(
    session: AsyncSession, *, user_id: int, provider: str
) -> None:
    """Serialize concurrent refreshes for one (user, provider).

    On Postgres, takes a transaction-scoped advisory lock that auto-
    releases at commit/rollback, so two coroutines that both see the
    token expired can't both call the provider and clobber each other's
    rotated refresh token. On SQLite (single-threaded test harness) this
    is a no-op — there is no concurrent writer to guard against.
    """
    if session.bind is None or session.bind.dialect.name != "postgresql":
        return
    key = _advisory_lock_key(user_id, provider)
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:k)"), {"k": key}
    )


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


def _fresh_token_if_valid(
    cred: OAuthCredential, moment: datetime
) -> FreshAccessToken | None:
    """Return a usable bearer if the stored token isn't (near-)expired.

    Returns ``None`` when the token is missing an expiry or sits within
    ``EXPIRY_GRACE`` of it, signalling the caller to refresh.
    """
    expires_at = cred.expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at is None or expires_at - EXPIRY_GRACE <= moment:
        return None
    return FreshAccessToken(
        access_token=decrypt(cred.access_token_ciphertext),
        expires_at=expires_at,
        account_email=cred.account_email,
    )


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

    fresh = _fresh_token_if_valid(cred, moment)
    if fresh is not None:
        return fresh

    # Token looks stale. Serialize the refresh across coroutines /
    # replicas before touching the provider: two callers that both saw it
    # expired must not both call the provider and clobber each other's
    # rotated refresh token (hubspot / pipedrive / outlook rotate it).
    await _acquire_refresh_lock(
        session, user_id=user_id, provider=provider
    )
    # Re-read the row now that we hold the lock — another coroutine may
    # have refreshed it while we waited. This double-check is the whole
    # point: if it is fresh now, return it without calling the provider.
    await session.refresh(cred)
    fresh = _fresh_token_if_valid(cred, moment)
    if fresh is not None:
        return fresh

    if not cred.refresh_token_ciphertext:
        raise OAuthStoreError(
            "access token expired and no refresh token is on file — "
            "ask the user to reconnect"
        )

    settings = get_settings()
    new_access: str
    new_expires: datetime
    new_scope: str | None
    new_refresh: str | None = None
    if provider == "gmail":
        try:
            tokens: TokenSet = await refresh_access_token(
                decrypt(cred.refresh_token_ciphertext),
                client_id=settings.google_oauth_client_id,
                client_secret=settings.google_oauth_client_secret,
            )
        except GmailError as exc:
            raise OAuthStoreError(f"refresh failed: {exc}") from exc
        new_access = tokens.access_token
        new_expires = tokens.expires_at
        new_scope = tokens.scope
    elif provider == "hubspot":
        try:
            hubspot_tokens: HubspotTokenSet = await refresh_hubspot_token(
                decrypt(cred.refresh_token_ciphertext),
                client_id=settings.hubspot_oauth_client_id,
                client_secret=settings.hubspot_oauth_client_secret,
            )
        except HubspotError as exc:
            raise OAuthStoreError(f"refresh failed: {exc}") from exc
        new_access = hubspot_tokens.access_token
        new_expires = hubspot_tokens.expires_at
        new_scope = hubspot_tokens.scope
        new_refresh = hubspot_tokens.refresh_token
    elif provider == "pipedrive":
        try:
            pd_tokens: PipedriveTokenSet = await refresh_pipedrive_token(
                decrypt(cred.refresh_token_ciphertext),
                client_id=settings.pipedrive_oauth_client_id,
                client_secret=settings.pipedrive_oauth_client_secret,
            )
        except PipedriveError as exc:
            raise OAuthStoreError(f"refresh failed: {exc}") from exc
        new_access = pd_tokens.access_token
        new_expires = pd_tokens.expires_at
        new_scope = pd_tokens.scope
        new_refresh = pd_tokens.refresh_token
    elif provider == "outlook":
        try:
            ms_tokens: OutlookTokenSet = await refresh_outlook_token(
                decrypt(cred.refresh_token_ciphertext),
                client_id=settings.outlook_oauth_client_id,
                client_secret=settings.outlook_oauth_client_secret,
            )
        except OutlookError as exc:
            raise OAuthStoreError(f"refresh failed: {exc}") from exc
        new_access = ms_tokens.access_token
        new_expires = ms_tokens.expires_at
        new_scope = ms_tokens.scope
        new_refresh = ms_tokens.refresh_token
    else:
        raise OAuthStoreError(f"unknown oauth provider: {provider}")

    cred.access_token_ciphertext = encrypt(new_access)
    cred.expires_at = new_expires
    if new_scope is not None:
        cred.scope = new_scope
    if new_refresh and new_refresh.strip():
        cred.refresh_token_ciphertext = encrypt(new_refresh)
    elif new_refresh is not None:
        # Provider returned an empty / whitespace refresh token. Keep the
        # existing one rather than silently overwriting it with garbage —
        # the audit flagged this path as a silent integration killer.
        logger.warning(
            "oauth refresh for user=%s provider=%s returned an empty "
            "refresh token; keeping the existing one",
            user_id,
            provider,
        )
    cred.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(cred)
    return FreshAccessToken(
        access_token=new_access,
        expires_at=new_expires,
        account_email=cred.account_email,
    )
