"""user email accounts (Google OAuth + Gmail send)

Revision ID: 20260430_0022
Revises: 20260427_0021
Create Date: 2026-04-30 12:00:00

Stores per-user OAuth-linked mailboxes that Convioo can send outreach
through. Today only Google (Gmail) is wired in; the ``provider`` column
keeps the door open for Microsoft/Outlook later. Tokens are encrypted
at rest with ``GOOGLE_OAUTH_TOKEN_KEY`` (Fernet) when set.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260430_0022"
down_revision = "20260427_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_email_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("scopes", sa.Text(), nullable=False, server_default=""),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column(
            "token_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "token_encrypted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "provider", "email", name="uq_user_email_account"
        ),
    )
    op.create_index(
        "ix_user_email_accounts_user_provider",
        "user_email_accounts",
        ["user_id", "provider"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_email_accounts_user_provider",
        table_name="user_email_accounts",
    )
    op.drop_table("user_email_accounts")
