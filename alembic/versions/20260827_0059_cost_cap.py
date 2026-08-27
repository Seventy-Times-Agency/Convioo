"""team monthly cost cap

Revision ID: 20260827_0059
Revises: 20260827_0058
Create Date: 2026-08-27

Wave 1 задача 7: the owner's monthly $ ceiling for variable API
spend. NULL = no ceiling; 80% warns via Telegram, 100% stops
searches with a clear message.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260827_0059"
down_revision = "20260827_0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "teams",
        sa.Column("monthly_cost_cap_usd", sa.Numeric(10, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("teams", "monthly_cost_cap_usd")
