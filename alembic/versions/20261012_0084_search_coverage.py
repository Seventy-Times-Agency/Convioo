"""search_coverage — память о прочёсанных срезах карты (район × формулировка).

Revision ID: 20261012_0084
Revises: 20261011_0083
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261012_0084"
down_revision = "20261011_0083"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "search_coverage",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("scope_key", sa.String(64), nullable=False),
        sa.Column("niche_key", sa.String(120), nullable=False),
        sa.Column("region_key", sa.String(160), nullable=False),
        sa.Column("slice_key", sa.String(200), nullable=False),
        sa.Column("runs", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fresh", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("scope_key", "niche_key", "region_key", "slice_key", name="uq_search_coverage_slice"),
    )


def downgrade() -> None:
    op.drop_table("search_coverage")
