"""oauth credentials table for Gmail / Outlook send-as-user

Revision ID: 20260503_0032
Revises: 20260503_0031
Create Date: 2026-05-03 09:30:00

A separate table from ``user_integration_credentials`` because OAuth
needs a refresh-token + scope + expiry shape that the Notion-style
"single API token" rows don't have. Both ``access_token_ciphertext``
and ``refresh_token_ciphertext`` are Fernet-encrypted; nothing
plaintext is persisted.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260503_0032"
down_revision = "20260503_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "oauth_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column(
            "access_token_ciphertext", sa.Text(), nullable=False
        ),
        sa.Column(
            "refresh_token_ciphertext", sa.Text(), nullable=True
        ),
        sa.Column(
            "expires_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("account_email", sa.String(length=255), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "provider", name="uq_oauth_owner_provider"
        ),
    )


def downgrade() -> None:
    op.drop_table("oauth_credentials")
