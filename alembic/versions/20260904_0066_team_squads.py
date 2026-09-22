"""teams inside a company

Revision ID: 20260904_0066
Revises: 20260904_0065
Create Date: 2026-09-04

Компания (teams) получает деление на команды: у каждой свой тимлид
и свои селзы, лиды не пересекаются, сводка поднимается к РОПу и
владельцу. squad_id у участника NULL — общий пул: компании без
деления работают ровно как раньше.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260904_0066"
down_revision = "20260904_0065"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")


def upgrade() -> None:
    op.create_table(
        "team_squads",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column(
            "team_id",
            _UUID,
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column(
            "lead_user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("team_id", "name", name="uq_team_squads_name"),
    )
    op.create_index("ix_team_squads_team_id", "team_squads", ["team_id"])
    op.add_column(
        "team_memberships",
        sa.Column(
            "squad_id",
            _UUID,
            sa.ForeignKey("team_squads.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_team_memberships_squad_id", "team_memberships", ["squad_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_team_memberships_squad_id", "team_memberships")
    op.drop_column("team_memberships", "squad_id")
    op.drop_table("team_squads")
