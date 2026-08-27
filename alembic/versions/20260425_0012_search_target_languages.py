"""per-search target language filter

Revision ID: 20260425_0012
Revises: 20260425_0011
Create Date: 2026-04-26 00:00:00

Adds ``search_queries.target_languages`` — an optional list of BCP-47
language codes (``["ru", "uk"]``, ``["en"]``, ...) the salesperson
wants their leads to operate in. Empty / null means no language
preference (default).

The pipeline reads this and (a) filters Google Maps results with a
script-based heuristic, (b) feeds the value to Claude so the AI
scorer downgrades leads that don't match.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision = "20260425_0012"
down_revision = "20260425_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        col_type = JSONB()
    else:
        col_type = sa.JSON()
    op.add_column(
        "search_queries",
        sa.Column("target_languages", col_type, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("search_queries", "target_languages")
