"""per-user color marks on leads + scope team views to caller

Revision ID: 20260425_0009
Revises: 20260425_0008
Create Date: 2026-04-25 21:00:00

Two related changes:

- ``lead_marks`` table — each (user_id, lead_id) pair can carry one
  short colour tag the user picks privately. Colours have no fixed
  meaning; one teammate can paint a lead red because they're chasing
  it, another can paint the same lead blue because it's a low priority
  for them. Marks never propagate.
- The list endpoints already gate by ``team_id``; from this revision
  on they also filter to the caller's user_id by default so members
  only see their own searches inside a team. Owners pass an explicit
  ``member_user_id`` to drill into another teammate's CRM.

The DB-side change is only the new table — the filter behaviour is
enforced in the API layer.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260425_0009"
down_revision = "20260425_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lead_marks",
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("lead_id", sa.CHAR(length=36), nullable=False),
        sa.Column("color", sa.String(length=16), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "lead_id", name="uq_lead_marks_user_lead"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_lead_marks_user_id", "lead_marks", ["user_id"], unique=False
    )
    op.create_index(
        "ix_lead_marks_lead_id", "lead_marks", ["lead_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_lead_marks_lead_id", table_name="lead_marks")
    op.drop_index("ix_lead_marks_user_id", table_name="lead_marks")
    op.drop_table("lead_marks")
