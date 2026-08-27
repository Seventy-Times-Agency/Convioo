"""team descriptions + per-member descriptions + cross-team lead dedup

Revision ID: 20260425_0011
Revises: 20260425_0010
Create Date: 2026-04-25 23:30:00

Three additions to support the team-context Henry persona and the
hard "no lead twice in one team" rule:

- ``teams.description`` — short purpose text the owner sets so
  Henry knows what the team is for and members understand the scope.
- ``team_memberships.description`` — owner-curated short note
  about each member ("Анна — закрывает стоматологии в EU").
- ``team_seen_leads`` — every lead returned to anyone in a team is
  fingerprinted here. The pipeline filters incoming Google Maps
  results against this table when a team-mode search runs, so the
  same place never appears twice across teammates.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260425_0011"
down_revision = "20260425_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("teams", sa.Column("description", sa.Text(), nullable=True))
    op.add_column(
        "team_memberships",
        sa.Column("description", sa.Text(), nullable=True),
    )

    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # Pick the right team_id type up front so CREATE TABLE doesn't
    # have to fight Postgres on a CHAR(36) → UUID FK mismatch with
    # teams.id (which migration 0010 already converted to native UUID).
    # SQLite test harness keeps CHAR(36) — _UUID decorator handles it.
    team_id_type: sa.types.TypeEngine = (
        postgresql.UUID(as_uuid=True) if is_postgres else sa.CHAR(length=36)
    )

    op.create_table(
        "team_seen_leads",
        sa.Column("team_id", team_id_type, nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=256), nullable=False),
        sa.Column("first_user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("team_id", "source", "source_id"),
        # FK to teams.id is added separately below — it can only be
        # created once team_id has the matching native UUID type on
        # Postgres. first_user_id is a plain BIGINT FK so it stays
        # inline.
        sa.ForeignKeyConstraint(
            ["first_user_id"], ["users.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_team_seen_leads_team_id",
        "team_seen_leads",
        ["team_id"],
        unique=False,
    )

    op.create_foreign_key(
        "team_seen_leads_team_id_fkey",
        "team_seen_leads",
        "teams",
        ["team_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_index("ix_team_seen_leads_team_id", table_name="team_seen_leads")
    op.drop_table("team_seen_leads")
    op.drop_column("team_memberships", "description")
    op.drop_column("teams", "description")
