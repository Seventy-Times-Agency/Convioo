"""saved + scheduled searches

Revision ID: 20260503_0034
Revises: 20260503_0033
Create Date: 2026-05-03 11:00:00

Bookmark a discovery query and (optionally) re-run it on a recurring
schedule. ``schedule_cron = NULL`` means manual-run-only — the row
exists only as a rename-and-replay shortcut.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260503_0034"
down_revision = "20260503_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saved_searches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "team_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("niche", sa.String(length=256), nullable=False),
        sa.Column("region", sa.String(length=256), nullable=False),
        sa.Column(
            "target_languages", postgresql.JSONB(), nullable=True
        ),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("radius_m", sa.Integer(), nullable=True),
        sa.Column("max_results", sa.SmallInteger(), nullable=True),
        # Free-form recurrence label: "off" / "daily" / "weekly" /
        # "biweekly" / "monthly". We compute next_run_at from this on
        # save, so the worker only ever consults next_run_at.
        sa.Column("schedule", sa.String(length=16), nullable=True),
        sa.Column(
            "next_run_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "last_run_at", sa.DateTime(timezone=True), nullable=True
        ),
        # Tracking metric for the UI's "12 new since last run" badge.
        sa.Column(
            "last_leads_count", sa.Integer(), nullable=True
        ),
        sa.Column(
            "active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
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
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_saved_searches_due",
        "saved_searches",
        ["next_run_at"],
        postgresql_where=sa.text("active = true AND schedule IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_saved_searches_due", table_name="saved_searches"
    )
    op.drop_table("saved_searches")
