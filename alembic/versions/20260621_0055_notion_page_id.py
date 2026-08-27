"""notion_page_id on leads

Revision ID: 20260621_0055
Revises: 20260621_0054
Create Date: 2026-06-21 01:00:00

Adds ``notion_page_id`` to ``leads`` — set when a lead is exported to a
Notion database so subsequent status updates can be pushed back and
Notion changes can be pulled into Convioo on demand.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260621_0055"
down_revision = "20260621_0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("notion_page_id", sa.String(100), nullable=True),
    )
    op.create_index(
        "ix_leads_notion_page_id", "leads", ["notion_page_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_leads_notion_page_id", table_name="leads")
    op.drop_column("leads", "notion_page_id")
