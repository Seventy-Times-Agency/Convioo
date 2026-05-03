"""per-search source overrides

Revision ID: 20260503_0036
Revises: 20260503_0035
Create Date: 2026-05-03 12:00:00

A nullable JSONB column on ``search_queries`` storing the subset of
{google, osm, yelp, foursquare} the user enabled for this run. NULL
= honour the global *_ENABLED env flags (default behavior). Lets the
caller skip a source that's hot-rate-limited today without rotating
env vars.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260503_0036"
down_revision = "20260503_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "search_queries",
        sa.Column(
            "enabled_sources", postgresql.JSONB(), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("search_queries", "enabled_sources")
