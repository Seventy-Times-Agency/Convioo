"""user integration credentials

Revision ID: 20260502_0025
Revises: 20260502_0024
Create Date: 2026-05-02 18:00:00

Per-user encrypted credentials for outbound integrations (Notion
first; Gmail / HubSpot / Pipedrive can plug in later). The ``token``
column stores Fernet-encrypted bytes — at-rest leaks of the DB don't
expose the upstream API tokens.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260502_0025"
down_revision = "20260502_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_integration_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("token_ciphertext", sa.Text(), nullable=False),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
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
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "provider", name="uq_user_integration_owner_provider"
        ),
    )


def downgrade() -> None:
    op.drop_table("user_integration_credentials")
