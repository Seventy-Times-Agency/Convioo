"""add icp_profile to users

Revision ID: 20260506_0044
Revises: 20260506_0043
Create Date: 2026-05-06 00:44:00
"""

import sqlalchemy as sa
from alembic import op

revision = "20260506_0044"
down_revision = "20260506_0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("icp_profile", sa.JSON, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "icp_profile")
