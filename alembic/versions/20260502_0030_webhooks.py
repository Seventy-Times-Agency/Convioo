"""outbound webhook subscriptions

Revision ID: 20260502_0030
Revises: 20260502_0029
Create Date: 2026-05-02 22:30:00

Per-user webhook destinations the platform POSTs to when an event
fires (lead.created / lead.status_changed / search.finished). Each
row carries an HMAC secret used to sign every dispatch so the
receiver can verify authenticity. ``failure_count`` tracks
consecutive failures so we can auto-disable a flaky URL.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260502_0030"
down_revision = "20260502_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webhooks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("target_url", sa.String(length=2048), nullable=False),
        sa.Column("secret", sa.String(length=128), nullable=False),
        sa.Column("event_types", postgresql.JSONB(), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=True),
        sa.Column(
            "active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "failure_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "last_delivery_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "last_delivery_status", sa.SmallInteger(), nullable=True
        ),
        sa.Column(
            "last_failure_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("last_failure_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_webhooks_user_active",
        "webhooks",
        ["user_id", "active"],
    )


def downgrade() -> None:
    op.drop_index("ix_webhooks_user_active", table_name="webhooks")
    op.drop_table("webhooks")
