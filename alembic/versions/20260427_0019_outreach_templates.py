"""outreach_templates — saved cold-email / follow-up boilerplate

Revision ID: 20260427_0019
Revises: 20260427_0018
Create Date: 2026-04-27 06:00:00

Adds the table backing the user-managed outreach template library.
Each row is scoped to a user and optionally to a team (team_id NULL
= personal template; team_id set = shared with the whole team).
``body`` accepts placeholders like ``{name}`` / ``{niche}`` /
``{region}`` that the frontend substitutes when the user applies a
template to a specific lead.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260427_0019"
down_revision = "20260427_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outreach_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "tone",
            sa.String(length=32),
            server_default=sa.text("'professional'"),
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
        "ix_outreach_templates_user_id",
        "outreach_templates",
        ["user_id"],
    )
    op.create_index(
        "ix_outreach_templates_team_id",
        "outreach_templates",
        ["team_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_outreach_templates_team_id", table_name="outreach_templates"
    )
    op.drop_index(
        "ix_outreach_templates_user_id", table_name="outreach_templates"
    )
    op.drop_table("outreach_templates")
