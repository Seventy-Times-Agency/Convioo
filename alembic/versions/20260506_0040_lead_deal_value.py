"""add deal_value to leads

Revision ID: 20260506_0040
Revises: 20260506_0039
Create Date: 2026-05-06 00:40:00

Stores the estimated deal value for a lead so teams can see pipeline
totals in the CRM without exporting to a spreadsheet.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260506_0040"
down_revision = "20260506_0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("deal_value", sa.Numeric(12, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("leads", "deal_value")
