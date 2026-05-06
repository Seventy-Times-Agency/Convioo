"""add google_sheets_spreadsheet_id to users

Revision ID: 20260506_0043
Revises: 20260506_0042
Create Date: 2026-05-06 00:43:00
"""

import sqlalchemy as sa
from alembic import op

revision = "20260506_0043"
down_revision = "20260506_0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("google_sheets_spreadsheet_id", sa.String(200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "google_sheets_spreadsheet_id")
