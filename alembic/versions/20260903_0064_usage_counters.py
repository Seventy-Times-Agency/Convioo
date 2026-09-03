"""durable usage counters

Revision ID: 20260903_0064
Revises: 20260901_0063
Create Date: 2026-09-03

Счётчики затрат переезжают из TTL-кэша в базу: кэш обнулялся при
редеплое, не разделялся между API и воркером без Redis, а его
инкремент терял обновления под параллельным обогащением. На этих
цифрах стоит потолок затрат — теперь строка (user, service, day)
с атомарным UPSERT-инкрементом на стороне БД.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260903_0064"
down_revision = "20260901_0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usage_counters",
        sa.Column("user_id", sa.String(32), primary_key=True),
        sa.Column("service", sa.String(40), primary_key=True),
        sa.Column("day", sa.String(8), primary_key=True),
        sa.Column(
            "units", sa.BigInteger(), nullable=False, server_default="0"
        ),
    )
    op.create_index(
        "ix_usage_counters_user_day", "usage_counters", ["user_id", "day"]
    )


def downgrade() -> None:
    op.drop_table("usage_counters")
