"""dedup leads across runs and prevent concurrent active searches

Revision ID: 20260423_0004
Revises: 20260423_0003
Create Date: 2026-04-23 12:00:00

Adds:
- `user_seen_leads` table to remember every (user_id, source, source_id)
  tuple a user has already received, so re-running the same query doesn't
  return the same companies.
- Partial unique index on `search_queries(user_id)` where status is
  pending/running, so a user can't start a second search while one is
  already executing (catches the "tap the button 10 times" footgun).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260423_0004"
down_revision = "20260423_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_seen_leads",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=256), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("user_id", "source", "source_id"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_user_seen_leads_user_id",
        "user_seen_leads",
        ["user_id"],
        unique=False,
    )

    # Partial unique index: one active search per user at a time.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_active_search "
        "ON search_queries(user_id) "
        "WHERE status IN ('pending', 'running')"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_user_active_search")
    op.drop_index("ix_user_seen_leads_user_id", table_name="user_seen_leads")
    op.drop_table("user_seen_leads")
