"""lead feedback (fit / not_fit) for ICP refinement

Revision ID: 20260430_0023
Revises: 20260430_0022
Create Date: 2026-04-30 16:00:00

Records each user's per-lead "fit" / "not fit" verdict so the AI
scoring + cold-email prompts can mirror what the user actually
considers a good prospect. One verdict per (user_id, lead_id);
re-marking a lead just updates the row.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260430_0023"
down_revision = "20260430_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lead_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("verdict", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
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
            ["lead_id"], ["leads.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "lead_id", name="uq_lead_feedback_user_lead"
        ),
    )
    op.create_index(
        "ix_lead_feedback_user_recent",
        "lead_feedback",
        ["user_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_lead_feedback_user_recent", table_name="lead_feedback"
    )
    op.drop_table("lead_feedback")
