"""saved CRM segments / smart views per user

Revision ID: 20260503_0033
Revises: 20260503_0032
Create Date: 2026-05-03 10:30:00

A "segment" is a stored bundle of CRM filters — status, tag ids,
temperature, smart-filter preset, full-text query — saved by the
user so they can flip back to a complex view in one click. Lives
on the user (or team, NULLABLE) so collaborators on the same team
share their saved views.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260503_0033"
down_revision = "20260503_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lead_segments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "team_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("filter_json", postgresql.JSONB(), nullable=False),
        sa.Column(
            "sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False
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
        "ix_lead_segments_owner",
        "lead_segments",
        ["user_id", "team_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_lead_segments_owner", table_name="lead_segments")
    op.drop_table("lead_segments")
