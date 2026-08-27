"""teams + team memberships — groundwork for multi-user agency accounts

Revision ID: 20260423_0005
Revises: 20260423_0004
Create Date: 2026-04-23 20:00:00

Adds two tables that the web UI will wire up (user signup creates a
personal team; adding a teammate just inserts a row here). Nothing in
the Telegram flow reads/writes them yet — this migration is a
structural no-op for existing bot users.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260423_0005"
down_revision = "20260423_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "plan",
            sa.String(length=32),
            server_default=sa.text("'free'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "queries_used",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "queries_limit",
            sa.Integer(),
            server_default=sa.text("5"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "team_memberships",
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("team_id", sa.CHAR(length=36), nullable=False),
        sa.Column(
            "role",
            sa.String(length=32),
            server_default=sa.text("'member'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "team_id", name="uq_membership_user_team"),
    )
    op.create_index(
        "ix_team_memberships_user_id",
        "team_memberships",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_team_memberships_team_id",
        "team_memberships",
        ["team_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_team_memberships_team_id", table_name="team_memberships")
    op.drop_index("ix_team_memberships_user_id", table_name="team_memberships")
    op.drop_table("team_memberships")
    op.drop_table("teams")
