"""add archived_at to search_queries

Revision ID: 20260507_0048
Revises: 20260507_0047
Create Date: 2026-05-07 19:30:00

Sessions (search_queries) get the same soft-archive treatment as
leads: ``archived_at`` set means the session and its leads disappear
from the main workspace (CRM, kanban, sessions list). Dedup tables
(user_seen_leads / team_seen_leads) remain untouched, so an archived
session still blocks the same companies from re-appearing in fresh
searches.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260507_0048"
down_revision = "20260507_0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "search_queries",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_search_queries_archived_at",
        "search_queries",
        ["archived_at"],
        postgresql_where=sa.text("archived_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_search_queries_archived_at", table_name="search_queries"
    )
    op.drop_column("search_queries", "archived_at")
