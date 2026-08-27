"""search radius and scope

Revision ID: 20260502_0026
Revises: 20260502_0025
Create Date: 2026-05-02 19:00:00

Adds the geo-shape parameters to ``search_queries`` so the pipeline
can run "10 km around Berlin", "all of Bavaria", or "all of Germany"
without redefining the whole search shape:

- ``scope`` — one of ``city``, ``metro``, ``state``, ``country``.
  Drives how the geocode + collector locationRestriction get built.
  Default is ``city`` so existing rows behave identically to
  pre-migration runs.
- ``radius_m`` — search radius in metres when scope ∈ {city, metro};
  null otherwise. Bounded server-side at 100 km to keep Places API
  responses bounded.
- ``center_lat`` / ``center_lon`` — Nominatim geocode result, cached
  on the row so a re-run uses the same anchor point even if the
  city name resolves to a different lat/lon later.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260502_0026"
down_revision = "20260502_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "search_queries",
        sa.Column(
            "scope",
            sa.String(length=16),
            server_default=sa.text("'city'"),
            nullable=False,
        ),
    )
    op.add_column(
        "search_queries",
        sa.Column("radius_m", sa.Integer(), nullable=True),
    )
    op.add_column(
        "search_queries",
        sa.Column("center_lat", sa.Float(), nullable=True),
    )
    op.add_column(
        "search_queries",
        sa.Column("center_lon", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("search_queries", "center_lon")
    op.drop_column("search_queries", "center_lat")
    op.drop_column("search_queries", "radius_m")
    op.drop_column("search_queries", "scope")
