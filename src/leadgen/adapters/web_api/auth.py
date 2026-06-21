"""Auth machinery for the web API.

Two unrelated mechanisms live side by side here:

- ``require_api_key`` — legacy ``X-API-Key`` header check. Still
  guards the SSE progress stream because the EventSource API in the
  browser can't send cookies cross-origin without explicit setup.
- The session-cookie helpers below — opaque token in a httpOnly
  cookie, hash stored in ``user_sessions``. This is the path real
  end users authenticate over: register / login put the cookie,
  every authenticated endpoint reads it.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Cookie, Header, HTTPException, Request, Response, status
from sqlalchemy import select, update

from leadgen.config import get_settings
from leadgen.db.models import User, UserSession

# 30-day rolling cookie. On each authenticated use we refresh
# ``last_seen_at`` and slide ``expires_at`` forward to now + the window,
# so a session dies ``auth_session_days`` after the LAST activity rather
# than after login. To keep the write cheap we only slide (and re-issue
# the cookie) once more than ``SESSION_SLIDE_THROTTLE`` has elapsed since
# the last slide — see ``load_session``. The window length is tunable via
# ``Settings.auth_session_days``.
COOKIE_NAME = "convioo_session"
# Don't touch the DB / re-issue the cookie on every request: only slide
# the expiry once it would move by at least this much. With a 30-day
# window this means at most one extra UPDATE per active session per day.
SESSION_SLIDE_THROTTLE = timedelta(days=1)
LOCKOUT_THRESHOLD = 10
LOCKOUT_DURATION = timedelta(minutes=15)


# ── X-API-Key (legacy, only for SSE) ────────────────────────────────────

async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = get_settings().web_api_key
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Web API is not configured: WEB_API_KEY is empty. "
                "Set it in the Railway service vars to enable write endpoints."
            ),
        )
    if x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing X-API-Key header",
        )


# ── Session helpers ─────────────────────────────────────────────────────


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _token_hmac_key() -> bytes:
    """Server-side secret used to HMAC session / API-key tokens.

    Derived from ``AUTH_JWT_SECRET`` (the existing webserver secret).
    Keeping the binding to a settings value rather than a literal makes
    rotating the secret a one-line operator change — every active
    session / API key invalidates and reissues automatically.
    """
    return hashlib.sha256(
        get_settings().auth_jwt_secret.encode("utf-8")
    ).digest()


def hash_token(token: str) -> str:
    """Hash a session / API-key token for at-rest storage.

    HMAC-SHA256 keyed by a server-side secret. A leaked
    ``user_sessions`` / ``user_api_keys`` table on its own no longer
    yields the lookup hash an attacker would need: without the secret
    they cannot recompute the HMAC for a guessed token. Still O(1) at
    the storage layer (constant-time string, indexed equality).
    """
    return hmac.new(
        _token_hmac_key(), token.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def legacy_hash_token(token: str) -> str:
    """Plain SHA-256 of the token. Used to look up rows that were
    persisted before the HMAC switch so existing sessions / API keys
    keep working through the migration. New writes always use the
    keyed ``hash_token``.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def request_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()[:64]
    if request.client and request.client.host:
        return request.client.host[:64]
    return None


def request_user_agent(request: Request | None) -> str | None:
    if request is None:
        return None
    ua = request.headers.get("user-agent")
    return ua[:256] if ua else None


def device_fingerprint(ip: str | None, user_agent: str | None) -> str:
    """Stable per-(rough-network, browser) fingerprint.

    For new-device detection we don't want every NAT IP rotation to
    look like a fresh login. Truncate IPv4 to /24 (last octet zeroed)
    and IPv6 to /48 (top three groups), then hash with the UA.
    """
    netbase = ""
    if ip:
        if ":" in ip:
            parts = ip.split(":")
            netbase = ":".join(parts[:3])
        else:
            parts = ip.split(".")
            netbase = ".".join(parts[:3]) + ".0" if len(parts) == 4 else ip
    payload = f"{netbase}|{user_agent or ''}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:64]


def _is_secure(request: Request | None) -> bool:
    """Decide whether to set the Secure cookie flag.

    HTTPS in production (Vercel/Railway) → Secure=True. Plain HTTP
    in local dev → Secure=False so the cookie still attaches.
    """
    if request is None:
        return True
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    return proto == "https"


def set_session_cookie(
    response: Response, token: str, *, request: Request | None = None
) -> None:
    days = max(1, get_settings().auth_session_days)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=days * 86400,
        httponly=True,
        secure=_is_secure(request),
        samesite="lax",
        path="/",
    )


def clear_session_cookie(
    response: Response, *, request: Request | None = None
) -> None:
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        secure=_is_secure(request),
        samesite="lax",
    )


async def create_session(
    db_session,
    *,
    user_id: int,
    request: Request | None = None,
) -> tuple[str, UserSession]:
    """Create a fresh ``user_sessions`` row and return ``(token, row)``.

    The token must be sent to the client via ``set_session_cookie``;
    only the SHA-256 hash lives in the DB.
    """
    token = secrets.token_urlsafe(32)
    days = max(1, get_settings().auth_session_days)
    ip = request_ip(request)
    ua = request_user_agent(request)
    row = UserSession(
        user_id=user_id,
        token_hash=hash_token(token),
        device_fingerprint=device_fingerprint(ip, ua),
        ip=ip,
        user_agent=ua,
        expires_at=_utcnow() + timedelta(days=days),
    )
    db_session.add(row)
    await db_session.flush()
    return token, row


async def revoke_session(db_session, session_id) -> None:
    await db_session.execute(
        update(UserSession)
        .where(UserSession.id == session_id)
        .where(UserSession.revoked_at.is_(None))
        .values(revoked_at=_utcnow())
    )


async def revoke_all_sessions(
    db_session, *, user_id: int, except_session_id=None
) -> int:
    """Revoke every active session for ``user_id``.

    Returns the number of sessions revoked. ``except_session_id`` lets
    "log out everywhere except here" leave the current device alive.
    """
    stmt = (
        update(UserSession)
        .where(UserSession.user_id == user_id)
        .where(UserSession.revoked_at.is_(None))
        .values(revoked_at=_utcnow())
    )
    if except_session_id is not None:
        stmt = stmt.where(UserSession.id != except_session_id)
    result = await db_session.execute(stmt)
    return result.rowcount or 0


def _maybe_slide_expiry(row: UserSession, now: datetime) -> bool:
    """Slide ``row.expires_at`` forward to ``now + window`` when it would
    move meaningfully. Returns True iff the row was extended.

    Throttled: we only extend once the remaining lifetime has dropped
    below ``window - SESSION_SLIDE_THROTTLE`` (i.e. more than the throttle
    has elapsed since the last extension). That keeps the rolling session
    genuinely activity-based while avoiding a DB write on every request.
    """
    days = max(1, get_settings().auth_session_days)
    window = timedelta(days=days)
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    # Remaining lifetime; once it slips under (window - throttle) we slide.
    if expires - now < window - SESSION_SLIDE_THROTTLE:
        row.expires_at = now + window
        return True
    return False


async def load_session(
    db_session, token: str
) -> tuple[UserSession | None, bool]:
    """Resolve a raw cookie token to its DB row, or ``None`` if invalid.

    Returns ``(row, extended)`` where ``extended`` is True when the
    session's ``expires_at`` was slid forward on this call (so the caller
    can re-issue the cookie with a fresh ``max_age``).

    Looks the row up by either the current HMAC hash or the legacy
    SHA-256 hash so sessions issued before the HMAC switch keep
    working. On a legacy hit the row is upgraded in place. A session
    unused past its (rolling) window still expires.
    """
    new_hash = hash_token(token)
    legacy_hash = legacy_hash_token(token)
    row = (
        await db_session.execute(
            select(UserSession)
            .where(UserSession.token_hash.in_([new_hash, legacy_hash]))
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return None, False
    if row.revoked_at is not None:
        return None, False
    now = _utcnow()
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if now >= expires:
        return None, False
    if row.token_hash != new_hash:
        row.token_hash = new_hash
    extended = _maybe_slide_expiry(row, now)
    return row, extended


# ── FastAPI dependencies ────────────────────────────────────────────────


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.strip().split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip() or None
    return None


async def _resolve_api_key(db_session, token: str) -> User | None:
    """Look up a user by their API-key bearer token.

    SHA-256 hashed in storage; ``UserApiKey.revoked_at`` IS NULL is
    the active filter. Touches ``last_used_at`` so the Settings → API
    keys UI shows useful telemetry.
    """
    from leadgen.db.models import UserApiKey

    new_hash = hash_token(token)
    legacy_hash = legacy_hash_token(token)
    row = (
        await db_session.execute(
            select(UserApiKey)
            .where(UserApiKey.token_hash.in_([new_hash, legacy_hash]))
            .where(UserApiKey.revoked_at.is_(None))
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    user = await db_session.get(User, row.user_id)
    if user is None:
        return None
    row.last_used_at = _utcnow()
    if row.token_hash != new_hash:
        row.token_hash = new_hash
    return user


async def get_current_user(
    request: Request,
    response: Response,
    convioo_session: str | None = Cookie(default=None, alias=COOKIE_NAME),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> User:
    """Resolve the caller to a ``User`` via cookie OR ``Authorization: Bearer``.

    Cookie path is the default for browser users (Phase 1 plumbing);
    Bearer path is for API consumers — Zapier, Make, scripts.
    Bearer wins when both are present, so a script that pastes a stale
    cookie alongside its API key still authenticates correctly.

    When the session's rolling expiry is slid forward (see
    ``load_session``), the ``convioo_session`` cookie is re-set on the
    injected ``Response`` so the browser keeps it alive for another full
    window. FastAPI merges this Response's headers into the endpoint's.
    """
    bearer = _extract_bearer(authorization)
    from leadgen.db.session import session_factory

    if bearer:
        async with session_factory() as db_session:
            user = await _resolve_api_key(db_session, bearer)
            if user is None:
                raise HTTPException(
                    status_code=401, detail="invalid or revoked API key"
                )
            await db_session.commit()
            request.state.user = user
            request.state.api_key_used = True
            return user

    if not convioo_session:
        raise HTTPException(status_code=401, detail="not authenticated")

    async with session_factory() as db_session:
        sess, extended = await load_session(db_session, convioo_session)
        if sess is None:
            raise HTTPException(status_code=401, detail="session invalid")
        user = await db_session.get(User, sess.user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="user gone")
        sess.last_seen_at = _utcnow()
        await db_session.commit()
        # When the rolling expiry was slid forward, re-issue the cookie so
        # the browser's max_age tracks the DB. The DB-side slide is the
        # security-critical part; this just keeps the client in sync.
        if extended:
            set_session_cookie(response, convioo_session, request=request)
        # Stash the session on the request so handlers can inspect it
        # (e.g. "revoke other sessions but keep mine").
        request.state.session_id = sess.id
        request.state.user = user
        return user


async def get_current_user_optional(
    request: Request,
    response: Response,
    convioo_session: str | None = Cookie(default=None, alias=COOKIE_NAME),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> User | None:
    """Like ``get_current_user`` but returns ``None`` instead of 401.

    Used by endpoints that have a public mode (e.g. invite preview).
    """
    if not convioo_session and not _extract_bearer(authorization):
        return None
    try:
        return await get_current_user(
            request, response, convioo_session, authorization
        )
    except HTTPException:
        return None


def current_session_id(request: Request):
    """Return the session UUID set by ``get_current_user`` or ``None``."""
    return getattr(request.state, "session_id", None)


# ── Lockout helpers ─────────────────────────────────────────────────────


def is_locked(user: User) -> bool:
    locked_until = user.locked_until
    if locked_until is None:
        return False
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=timezone.utc)
    return _utcnow() < locked_until


def record_failed_login(user: User) -> bool:
    """Increment failed-attempt counter; returns True iff just locked."""
    user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
    if user.failed_login_attempts >= LOCKOUT_THRESHOLD:
        user.locked_until = _utcnow() + LOCKOUT_DURATION
        return True
    return False


def clear_failed_logins(user: User) -> None:
    user.failed_login_attempts = 0
    user.locked_until = None


def enforce_rate_limit(
    limiter, *keys: str, retry_hint: int = 60
) -> None:
    """Reject the request with 429 if any of ``keys`` is over budget.

    ``keys`` is variadic so the caller can rate-limit on multiple axes
    at once — e.g. login enforces both per-IP and per-email throttles
    in the same call.
    """
    for key in keys:
        if not key:
            continue
        if not limiter.check_and_record(key):
            raise HTTPException(
                status_code=429,
                detail="too many attempts; try again later",
                headers={"Retry-After": str(retry_hint)},
            )


async def is_known_device(
    db_session, *, user_id: int, fingerprint: str, lookback_days: int = 60
) -> bool:
    """True if ``fingerprint`` already appears on a recent session."""
    cutoff = _utcnow() - timedelta(days=lookback_days)
    row = (
        await db_session.execute(
            select(UserSession.id)
            .where(UserSession.user_id == user_id)
            .where(UserSession.device_fingerprint == fingerprint)
            .where(UserSession.created_at >= cutoff)
            .limit(1)
        )
    ).scalar_one_or_none()
    return row is not None
