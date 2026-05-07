from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import _JSONB, _UUID, Base, _utcnow


class OAuthCredential(Base):
    """Encrypted OAuth tokens for outbound providers (Gmail / Outlook).

    One row per (user, provider). Both access_token and refresh_token
    are Fernet-encrypted; ``expires_at`` is stamped when we exchange
    the auth code so refresh-on-demand can decide whether the access
    token is still alive. Scope is recorded so we can re-prompt the
    user if the integration ever needs broader permissions.
    """

    __tablename__ = "oauth_credentials"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "provider", name="uq_oauth_owner_provider"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    access_token_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_ciphertext: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    scope: Mapped[str | None] = mapped_column(Text)
    account_email: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class UserIntegrationCredential(Base):
    """Encrypted credentials for an outbound provider (Notion / Gmail / etc).

    One row per (user, provider). ``token_ciphertext`` holds the
    Fernet-encrypted upstream token; the ``config`` JSONB carries
    provider-specific settings (e.g. Notion's ``database_id``).
    The plaintext token is never persisted — even a full DB dump
    leaks nothing that an attacker can replay.
    """

    __tablename__ = "user_integration_credentials"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "provider", name="uq_user_integration_owner_provider"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    token_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict[str, Any] | None] = mapped_column(_JSONB())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class Webhook(Base):
    """Outbound webhook subscription owned by a single user.

    On a registered event, the dispatcher POSTs JSON to ``target_url``
    and includes ``X-Convioo-Signature: sha256=<hex>``, the HMAC-SHA256
    of the body using ``secret``. Five consecutive failures auto-flip
    ``active`` to false so a dead URL stops retrying forever.
    """

    __tablename__ = "webhooks"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    secret: Mapped[str] = mapped_column(String(128), nullable=False)
    event_types: Mapped[list[str]] = mapped_column(
        _JSONB(), nullable=False, default=list
    )
    description: Mapped[str | None] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    failure_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    last_delivery_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    last_delivery_status: Mapped[int | None] = mapped_column(SmallInteger)
    last_failure_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    last_failure_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class StripeEvent(Base):
    """Idempotency log for processed Stripe webhook events.

    Stripe retries delivery on any non-2xx, so a successful upgrade
    that times out on the response can show up again. Inserting the
    event id with a unique PK lets us reject the second copy with a
    cheap ``IntegrityError`` instead of double-applying it.
    """

    __tablename__ = "stripe_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class AffiliateCode(Base):
    """Public slug a partner shares to attribute signups to themselves.

    The ``code`` IS the primary key — it's what shows up in the public
    URL ``/r/{code}``. ``percent_share`` is a hint for the (future)
    Stripe revenue-share automation; today it's just metadata.
    """

    __tablename__ = "affiliate_codes"

    code: Mapped[str] = mapped_column(
        String(64), primary_key=True, index=False
    )
    owner_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str | None] = mapped_column(String(128))
    percent_share: Mapped[int] = mapped_column(
        SmallInteger, default=30, nullable=False
    )
    active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class Referral(Base):
    """One row per signup that arrived through an ``AffiliateCode``.

    ``referred_user_id`` is unique so re-using a different /r/ URL
    can't double-count the same human. ``first_paid_at`` will be
    stamped by the Stripe webhook handler when the referred user
    becomes a paying customer.
    """

    __tablename__ = "referrals"
    __table_args__ = (
        UniqueConstraint(
            "referred_user_id", name="uq_referrals_referred_user"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("affiliate_codes.code", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    referred_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    signed_up_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    first_paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )


class AssistantMemory(Base):
    """Persistent memory for the floating Henry assistant.

    Two kinds of entries:
    - ``summary`` — Henry's distilled recap of a recent dialogue
      session (1-3 sentences). Written every N user messages.
    - ``fact`` — a single durable fact extracted from the dialogue
      (e.g. "продаёт SEO для дантистов в Берлине", "целевой
      сегмент — премиум-стоматологии"). Written alongside summaries.

    A row is scoped to a user and optionally to a team:
    - ``team_id`` IS NULL → personal-mode memory (only the user sees it).
    - ``team_id`` IS NOT NULL → team-scoped memory; available to every
      member of the team so Henry can coordinate (e.g. owner notes
      about the team strategy).
    """

    __tablename__ = "assistant_memories"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID(),
        ForeignKey("teams.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[dict[str, Any] | None] = mapped_column(_JSONB())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
