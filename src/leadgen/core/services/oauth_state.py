"""HMAC-signed, time-bounded OAuth ``state`` helpers.

The OAuth state parameter binds an in-flight authorize request to the
user that started it. If we just packed ``user_id`` into the state and
trusted the callback to read it back, an attacker could craft a
``"<victim_id>:..."`` callback and write their own provider tokens
under the victim's account.

These helpers sign the user_id with the server-side ``AUTH_JWT_SECRET``
so the callback can verify the state was actually issued by us, and
expire it in 15 minutes so a leaked state can't be redeemed forever.

This module is provider-agnostic — Notion, Gmail (future), Outlook,
HubSpot (future), Pipedrive (future) all use the same primitives.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time

# How long an unredeemed authorize-state stays valid. The user has to
# click "Allow" inside the provider within this window or the callback
# rejects the state. 15 minutes is generous enough for human clicks
# and tight enough that a leaked state isn't useful for long.
STATE_TTL_SEC = 15 * 60


class StateValidationError(RuntimeError):
    """Raised when an OAuth ``state`` is malformed, tampered, or expired.

    The caller treats this as a 400 with the same generic message for
    every failure mode — leaking the precise reason would let an
    attacker probe whether their forgery had the right signature
    structure.
    """


def issue_state(user_id: int, *, secret: str) -> str:
    """Mint a signed, time-stamped state token for the OAuth handshake.

    Format: ``"{user_id}:{nonce}:{ts}:{signature}"`` where ``signature``
    is a hex HMAC-SHA256 of ``"{user_id}:{nonce}:{ts}"`` keyed by the
    server-side ``secret``. Verification happens server-side via
    :func:`verify_state` — there is no DB-backed nonce table.
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


def verify_state(
    state: str, *, secret: str, max_age_sec: int = STATE_TTL_SEC
) -> int:
    """Return the ``user_id`` embedded in a valid state, or raise.

    Validates the HMAC signature in constant time and the timestamp
    window. Any malformed input, signature mismatch, expiry, or
    missing secret raises :class:`StateValidationError` so the route
    handler can return a uniform 400.
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
    return user_id
