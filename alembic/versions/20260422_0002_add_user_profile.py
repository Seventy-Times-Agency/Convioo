"""add user profile fields

Revision ID: 20260422_0002
Revises: 20260420_0001
Create Date: 2026-04-22 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260422_0002"
down_revision = "20260420_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("profession", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("service_description", sa.Text(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("home_region", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "niches",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column("onboarded_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "onboarded_at")
    op.drop_column("users", "niches")
    op.drop_column("users", "home_region")
    op.drop_column("users", "service_description")
    op.drop_column("users", "profession")
