"""team-scoped searches + invite tokens (10-minute TTL)

Revision ID: 20260425_0008
Revises: 20260425_0007
Create Date: 2026-04-25 18:00:00

Adds the multi-tenant seam:

- ``search_queries.team_id`` — when set, the search belongs to that
  team and is visible to every member. NULL = personal workspace,
  unchanged behaviour.
- ``team_invites`` — short-lived tokens an owner generates to bring a
  new teammate in. Token is unique, has an explicit ``expires_at`` so
  the API can reject stale ones, and stamps ``accepted_by_user_id`` /
  ``accepted_at`` once redeemed (single-use by convention).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260425_0008"
down_revision = "20260425_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "search_queries",
        sa.Column("team_id", sa.CHAR(length=36), nullable=True),
    )
    op.create_index(
        "ix_search_queries_team_id", "search_queries", ["team_id"], unique=False
    )
    op.create_foreign_key(
        "fk_search_queries_team_id",
        "search_queries",
        "teams",
        ["team_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_table(
        "team_invites",
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("team_id", sa.CHAR(length=36), nullable=False),
        sa.Column(
            "role",
            sa.String(length=32),
            server_default=sa.text("'member'"),
            nullable=False,
        ),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token", name="uq_team_invites_token"),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["accepted_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_team_invites_team_id", "team_invites", ["team_id"], unique=False
    )
    op.create_index(
        "ix_team_invites_token", "team_invites", ["token"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_team_invites_token", table_name="team_invites")
    op.drop_index("ix_team_invites_team_id", table_name="team_invites")
    op.drop_table("team_invites")

    op.drop_constraint(
        "fk_search_queries_team_id", "search_queries", type_="foreignkey"
    )
    op.drop_index("ix_search_queries_team_id", table_name="search_queries")
    op.drop_column("search_queries", "team_id")
