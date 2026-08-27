"""add rating_snapshots to leads

Revision ID: 20260506_0041
Revises: 20260506_0040
Create Date: 2026-05-06 00:41:00
"""

import sqlalchemy as sa
from alembic import op

revision = "20260506_0041"
down_revision = "20260506_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("rating_snapshots", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("leads", "rating_snapshots")
