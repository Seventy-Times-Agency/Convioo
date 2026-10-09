"""cost_prices — цены сервисов, которые владелец платформы правит в админке.

Revision ID: 20261011_0083
Revises: 20261010_0082
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261011_0083"
down_revision = "20261010_0082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cost_prices",
        sa.Column("service", sa.String(48), primary_key=True),
        sa.Column("price_usd", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("cost_prices")
