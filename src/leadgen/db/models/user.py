from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import _JSONB, _UUID, Base, _utcnow


class User(Base):
    __tablename__ = "users"

    # Telegram user id fits into BIGINT
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    last_name: Mapped[str | None] = mapped_column(String(128))
    email: Mapped[str | None] = mapped_column(String(255))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    language_code: Mapped[str | None] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    queries_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    queries_limit: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    # User profile — filled during onboarding, used to personalize AI advice
    display_name: Mapped[str | None] = mapped_column(String(64))
    age_range: Mapped[str | None] = mapped_column(String(16))
    # Optional. One of: 'male' | 'female' | 'other'. Drives Henry's
    # grammatical agreement (он/она) — never used for any kind of
    # filtering or personalisation beyond that.
    gender: Mapped[str | None] = mapped_column(String(16))
    business_size: Mapped[str | None] = mapped_column(String(32))
    profession: Mapped[str | None] = mapped_column(Text)
    service_description: Mapped[str | None] = mapped_column(Text)
    home_region: Mapped[str | None] = mapped_column(String(200))
    niches: Mapped[list[str] | None] = mapped_column(_JSONB())
    onboarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Stamped when the user finishes (or explicitly skips) the in-app
    # 4-step product tour. NULL = the tour will auto-open on next
    # ``/app`` visit; from Settings the user can clear it back to NULL
    # to replay the tour.
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    # Account recovery: optional secondary mailbox the user trusts to
    # always reach them, used by the forgot-email flow to remind them
    # which address their account is registered under.
    recovery_email: Mapped[str | None] = mapped_column(String(255))
    # Brute-force lockout state. ``failed_login_attempts`` resets to 0
    # on every successful login; once it reaches the lockout threshold
    # ``locked_until`` is stamped and login is refused (with the same
    # generic error message) until that time passes.
    failed_login_attempts: Mapped[int] = mapped_column(
        SmallInteger, default=0, nullable=False
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    # Platform-admin flag. Gates ``/api/v1/admin/*`` and the
    # ``/app/admin`` page. Promoted via SQL on Railway — no in-app
    # UI for granting it on day one.
    is_admin: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # Stripe link. ``stripe_customer_id`` is set on first checkout so
    # subsequent portal launches and webhook lookups don't need a
    # users-by-email scan. ``plan`` mirrors the active Stripe product
    # ("free" / "pro" / "agency") and ``plan_until`` is the current
    # period-end; both move from webhook events. ``trial_ends_at`` is
    # stamped at registration to grant a 14-day preview that bypasses
    # the quota check.
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64))
    plan: Mapped[str] = mapped_column(
        String(32), default="free", nullable=False
    )
    plan_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    trial_ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    # Notification preferences. ``daily_digest_enabled`` opts the user in
    # to a once-a-day summary email of new leads + replies. The cron
    # tick in ``queue/worker.py`` skips users who haven't opted in.
    # ``email_reply_tracking_enabled`` lets the worker poll Gmail (and
    # future Outlook) for replies to messages we sent on the user's
    # behalf, then logs them as ``LeadActivity(kind="email_replied")``.
    # Default is False on both — the user has to flip the toggle in
    # Settings → Notifications, otherwise we don't touch their inbox.
    daily_digest_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    email_reply_tracking_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    # Watermark for the periodic reply scanner so we never re-process
    # the same Gmail history page twice. Set on first scan, advanced as
    # we walk through pages.
    email_reply_last_history_id: Mapped[str | None] = mapped_column(
        String(64)
    )
    email_reply_last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    # Calendly or similar scheduling link. Injected into Henry's email
    # prompts so generated cold emails can mention booking options.
    calendly_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    google_sheets_spreadsheet_id: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )
    icp_profile: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    queries: Mapped[list[SearchQuery]] = relationship(back_populates="user")  # noqa: F821


class UserSession(Base):
    """A live login on a single device.

    The opaque session token (32 bytes of secrets.token_urlsafe) is
    stored ONLY in the user's httpOnly cookie. The DB keeps the
    SHA-256 hash so a database leak doesn't yield active sessions.

    ``device_fingerprint`` is SHA-256(user_agent || ip_subnet/24);
    it lets the login flow detect "first time we see this device" and
    fire a security-alert email without storing the raw IP forever.
    """

    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False
    )
    device_fingerprint: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )


class UserApiKey(Base):
    """Long-lived bearer token a user issues to themselves.

    Plaintext is shown once at creation and never persisted. ``token_hash``
    is the SHA-256 of the token; ``token_preview`` is a non-sensitive
    prefix/suffix stub for the UI ("convioo_pk_abc…xyz") so the user
    can recognise which key they're looking at without leaking it.
    """

    __tablename__ = "user_api_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False
    )
    token_preview: Mapped[str] = mapped_column(String(16), nullable=False)
    label: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )


class EmailVerificationToken(Base):
    """Short-lived single-use token for email verification or password reset.

    ``kind`` discriminates the purpose so future flows (password
    reset, email-change) reuse the same table. ``used_at`` flips the
    moment the user clicks the link, making the token spent.
    """

    __tablename__ = "email_verification_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(16), default="verify", nullable=False)
    token: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pending_email: Mapped[str | None] = mapped_column(String(255))


# PasswordResetToken is an alias for EmailVerificationToken (kind='reset').
# Kept so existing imports of ``PasswordResetToken`` continue to resolve.
PasswordResetToken = EmailVerificationToken


class UserAuditLog(Base):
    """Append-only audit trail of security-relevant user actions.

    Captures sign-in, profile updates, GDPR exports, account deletions,
    team-membership changes, etc. The ``ip`` column is best-effort —
    populated from request headers when available, NULL otherwise.
    """

    __tablename__ = "user_audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(256))
    payload: Mapped[dict | None] = mapped_column(_JSONB())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
