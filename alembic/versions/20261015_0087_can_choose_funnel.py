"""team_memberships.can_choose_funnel — продажник сам выбирает воронку.

Revision ID: 20261015_0087
Revises: 20261014_0086
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261015_0087"
down_revision = "20261014_0086"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "team_memberships",
        sa.Column("can_choose_funnel", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("team_memberships", "can_choose_funnel")
