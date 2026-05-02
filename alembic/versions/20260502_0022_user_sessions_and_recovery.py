"""user sessions and account recovery

Revision ID: 20260502_0022
Revises: 20260427_0021
Create Date: 2026-05-02 00:00:00

Phase 1 of the auth hardening — adds the building blocks needed for
forgot-password / forgot-email recovery and httpOnly-cookie sessions.

- ``user_sessions`` stores a SHA-256 hash of every issued opaque
  session token (the token itself only lives in the cookie). Each row
  records IP / user-agent / fingerprint so we can show the user where
  they're signed in and revoke specific devices.
- ``users`` gains ``recovery_email`` (used to recover account access
  when the primary mailbox is lost) plus ``failed_login_attempts`` and
  ``locked_until`` for brute-force lockout.
- ``email_verification_tokens.kind`` already accepts arbitrary 16-char
  values so the new ``password_reset`` and ``email_recovery`` kinds
  reuse the existing column unchanged.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260502_0022"
down_revision = "20260427_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column(
            "device_fingerprint", sa.String(length=64), nullable=True
        ),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=256), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_user_sessions_token_hash"),
    )
    op.create_index(
        "ix_user_sessions_user_active",
        "user_sessions",
        ["user_id", "revoked_at"],
    )
    op.create_index(
        "ix_user_sessions_user_fingerprint",
        "user_sessions",
        ["user_id", "device_fingerprint"],
    )

    op.add_column(
        "users",
        sa.Column("recovery_email", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "failed_login_attempts",
            sa.SmallInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "users",
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_attempts")
    op.drop_column("users", "recovery_email")

    op.drop_index(
        "ix_user_sessions_user_fingerprint", table_name="user_sessions"
    )
    op.drop_index("ix_user_sessions_user_active", table_name="user_sessions")
    op.drop_table("user_sessions")
