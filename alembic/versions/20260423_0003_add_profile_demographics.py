"""add demographic profile fields: display_name, age_range, business_size

Revision ID: 20260423_0003
Revises: 20260422_0002
Create Date: 2026-04-23 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260423_0003"
down_revision = "20260422_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Use batch ops with existing checks so reruns against an already-migrated
    # DB are safe (Railway has been wobbling between deploys).
    op.add_column(
        "users",
        sa.Column("display_name", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("age_range", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("business_size", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "business_size")
    op.drop_column("users", "age_range")
    op.drop_column("users", "display_name")
