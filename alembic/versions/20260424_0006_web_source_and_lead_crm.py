"""web-origin searches + lead CRM fields + seed web-demo user

Revision ID: 20260424_0006
Revises: 20260423_0005
Create Date: 2026-04-24 05:00:00

Adds the seam the web adapter needs to write lead history without
disturbing the Telegram flow:

- ``search_queries.source`` — "telegram" (default) vs "web"; lets the
  pipeline skip post-run Lead cleanup when a web consumer owns the row.
- ``leads.lead_status`` / ``owner_user_id`` / ``notes`` /
  ``last_touched_at`` — CRM state so the web "All leads" page can
  render status, assignee and notes without needing a separate events
  table yet.
- Seeds a synthetic ``users`` row (id=0, name="Web Demo") so web
  searches have a foreign-key target until real auth lands. Telegram
  user ids start at 1, so id=0 is free.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260424_0006"
down_revision = "20260423_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. SearchQuery.source
    op.add_column(
        "search_queries",
        sa.Column(
            "source",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'telegram'"),
        ),
    )
    op.create_index(
        "ix_search_queries_source", "search_queries", ["source"], unique=False
    )

    # 2. Lead CRM fields
    op.add_column(
        "leads",
        sa.Column(
            "lead_status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'new'"),
        ),
    )
    op.create_index("ix_leads_lead_status", "leads", ["lead_status"], unique=False)
    op.add_column(
        "leads", sa.Column("owner_user_id", sa.BigInteger(), nullable=True)
    )
    op.create_index(
        "ix_leads_owner_user_id", "leads", ["owner_user_id"], unique=False
    )
    op.create_foreign_key(
        "fk_leads_owner_user_id",
        "leads",
        "users",
        ["owner_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("leads", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column(
        "leads",
        sa.Column("last_touched_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 3. Seed the synthetic "web demo" user — FK target for web searches
    #    before auth lands. High quota so the open demo isn't billing-capped.
    op.execute(
        sa.text(
            """
            INSERT INTO users (id, first_name, queries_used, queries_limit, created_at)
            VALUES (0, 'Web Demo', 0, 100000, NOW())
            ON CONFLICT (id) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM users WHERE id = 0"))

    op.drop_column("leads", "last_touched_at")
    op.drop_column("leads", "notes")
    op.drop_constraint("fk_leads_owner_user_id", "leads", type_="foreignkey")
    op.drop_index("ix_leads_owner_user_id", table_name="leads")
    op.drop_column("leads", "owner_user_id")
    op.drop_index("ix_leads_lead_status", table_name="leads")
    op.drop_column("leads", "lead_status")

    op.drop_index("ix_search_queries_source", table_name="search_queries")
    op.drop_column("search_queries", "source")
