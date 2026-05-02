"""lead tags

Revision ID: 20260502_0024
Revises: 20260502_0023
Create Date: 2026-05-02 06:00:00

User-defined tags for leads — chips users attach to organize their CRM
beyond the hardcoded status enum. Each tag belongs to either a single
user (personal) or a team (shared); membership of leads is many-to-many.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260502_0024"
down_revision = "20260502_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lead_tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column(
            "color",
            sa.String(length=16),
            server_default=sa.text("'slate'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
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
        # Names are unique per (owner_user, team) so two members of a
        # team can't add competing "Ready to call" tags. Personal tags
        # (team_id IS NULL) collide only within the same user.
        sa.UniqueConstraint(
            "user_id", "team_id", "name", name="uq_lead_tags_owner_name"
        ),
    )
    op.create_index(
        "ix_lead_tags_team", "lead_tags", ["team_id"], unique=False
    )

    op.create_table(
        "lead_tag_assignments",
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tag_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["lead_id"], ["leads.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"], ["lead_tags.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("lead_id", "tag_id"),
    )
    op.create_index(
        "ix_lead_tag_assignments_tag",
        "lead_tag_assignments",
        ["tag_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_lead_tag_assignments_tag", table_name="lead_tag_assignments"
    )
    op.drop_table("lead_tag_assignments")
    op.drop_index("ix_lead_tags_team", table_name="lead_tags")
    op.drop_table("lead_tags")
