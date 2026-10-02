"""HMAC-signed, time-bounded OAuth ``state`` helpers.

The OAuth state parameter binds an in-flight authorize request to the
user that started it. If we just packed ``user_id`` into the state and
trusted the callback to read it back, an attacker could craft a
``"<victim_id>:..."`` callback and write their own provider tokens
under the victim's account.

These helpers sign the user_id with the server-side ``AUTH_JWT_SECRET``
so the callback can verify the state was actually issued by us, and
expire it in 15 minutes so a leaked state can't be redeemed forever.

This module is provider-agnostic — Notion, Gmail, Outlook, HubSpot,
Pipedrive all use the same primitives.

Replay protection (a redeemed state being submitted a second time
inside the TTL window) is backed by the ``oauth_consumed_nonces`` table
rather than a process-local set, so it holds across multiple web
replicas: the first replica to INSERT the nonce wins, every other
attempt hits the unique PK and is rejected.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.db.models import OAuthConsumedNonce

# How long an unredeemed authorize-state stays valid. The user has to
# click "Allow" inside the provider within this window or the callback
# rejects the state. 15 minutes is generous enough for human clicks
# and tight enough that a leaked state isn't useful for long.
STATE_TTL_SEC = 15 * 60

# Opportunistic garbage-collection of expired nonce rows is rate-limited
# so it doesn't fire a DELETE on every single callback. We sweep at most
# once per this interval (process-local timestamp — best-effort, the row
# count stays bounded by issued-states-per-TTL regardless).
_GC_INTERVAL_SEC = 5 * 60
_last_gc_at: float = 0.0


class StateValidationError(RuntimeError):
    """Raised when an OAuth ``state`` is malformed, tampered, or expired.

    The caller treats this as a 400 with the same generic message for
    every failure mode — leaking the precise reason would let an
    attacker probe whether their forgery had the right signature
    structure.
    """


async def _gc_consumed(session: AsyncSession, now: datetime) -> None:
    """Delete expired nonce rows, rate-limited to one sweep per interval.

    Best-effort: keeps the table from growing without bound while not
    issuing a DELETE on every redemption. The unique-PK replay check is
    independent of this, so a skipped sweep never weakens protection.
    """
    global _last_gc_at
    wall = time.time()
    if wall - _last_gc_at < _GC_INTERVAL_SEC:
        return
    _last_gc_at = wall
    await session.execute(
        delete(OAuthConsumedNonce).where(
            OAuthConsumedNonce.expires_at < now
        )
    )


async def _mark_consumed(
    session: AsyncSession, nonce: str, ts: int
) -> bool:
    """Record ``nonce`` as redeemed. Returns False on replay.

    Inserts the nonce into ``oauth_consumed_nonces``. The first caller
    (across all replicas) to land the row wins; a concurrent or repeated
    redemption hits the unique primary key and raises ``IntegrityError``,
    which we translate into a replay rejection.
    """
    now = datetime.now(timezone.utc)
    await _gc_consumed(session, now)

    expires_at = datetime.fromtimestamp(ts, tz=timezone.utc) + timedelta(
        seconds=STATE_TTL_SEC
    )
    row = OAuthConsumedNonce(nonce=nonce, expires_at=expires_at)
    session.add(row)
    try:
        await session.flush()
    except IntegrityError:
        # Already consumed (this replica or another). Roll back the failed
        # INSERT so the session stays usable for the caller's commit.
        await session.rollback()
        return False
    await session.commit()
    return True


def issue_state(user_id: int, *, secret: str) -> str:
    """Mint a signed, time-stamped state token for the OAuth handshake.

    Format: ``"{user_id}:{nonce}:{ts}:{signature}"`` where ``signature``
    is a hex HMAC-SHA256 of ``"{user_id}:{nonce}:{ts}"`` keyed by the
    server-side ``secret``. Verification happens server-side via
    :func:`verify_state`. The nonce store is touched only on redemption,
    so minting stays synchronous and DB-free.
    """
    if not secret:
        raise StateValidationError(
            "OAuth state secret is not configured (AUTH_JWT_SECRET)."
        )
    nonce = secrets.token_urlsafe(12)
    ts = str(int(time.time()))
    payload = f"{user_id}:{nonce}:{ts}"
    signature = hmac.new(
        secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return f"{payload}:{signature}"


async def verify_state(
    state: str,
    *,
    secret: str,
    session: AsyncSession,
    max_age_sec: int = STATE_TTL_SEC,
) -> int:
    """Return the ``user_id`` embedded in a valid state, or raise.

    Validates the HMAC signature in constant time and the timestamp
    window, then atomically marks the nonce consumed in the shared
    ``oauth_consumed_nonces`` table so a redeemed state can't be replayed
    through any replica. Any malformed input, signature mismatch, expiry,
    replay, or missing secret raises :class:`StateValidationError` so the
    route handler can return a uniform 400.
    """
    if not secret:
        raise StateValidationError(
            "OAuth state secret is not configured (AUTH_JWT_SECRET)."
        )
    if not state:
        raise StateValidationError("missing state")
    parts = state.split(":")
    if len(parts) != 4:
        raise StateValidationError("malformed state")
    user_id_str, nonce, ts_str, signature = parts
    if not nonce:
        raise StateValidationError("malformed state")
    payload = f"{user_id_str}:{nonce}:{ts_str}"
    expected = hmac.new(
        secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise StateValidationError("state signature mismatch")
    try:
        user_id = int(user_id_str)
        ts = int(ts_str)
    except ValueError as exc:
        raise StateValidationError("state numeric fields") from exc
    age = int(time.time()) - ts
    if age < 0 or age > max_age_sec:
        raise StateValidationError("state expired")
    if not await _mark_consumed(session, nonce, ts):
        raise StateValidationError("state already consumed")
    return user_id


# Re-export so test helpers and rare external callers can reference the
# count of currently-stored nonces without importing the model directly.
async def _consumed_count(session: AsyncSession) -> int:
    return int(
        (
            await session.execute(
                select(func.count()).select_from(OAuthConsumedNonce)
            )
        ).scalar_one()
    )
