"""teams: месячный бюджет как лимит токенов.

``token_stop_at_zero`` — команда сама решает, останавливать ли запуски
на нуле. ``tokens_refill_month`` — за какой месяц баланс уже пополнен
до бюджета (``YYYY-MM``), чтобы пополнение не повторялось.

Revision ID: 20261008_0075
Revises: 20261007_0074
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261008_0075"
down_revision = "20261007_0074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "teams",
        sa.Column("token_stop_at_zero", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("teams", sa.Column("tokens_refill_month", sa.String(7), nullable=True))


def downgrade() -> None:
    op.drop_column("teams", "tokens_refill_month")
    op.drop_column("teams", "token_stop_at_zero")
