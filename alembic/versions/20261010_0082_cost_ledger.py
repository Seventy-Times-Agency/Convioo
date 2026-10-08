"""cost_events + search_queries.economics — журнал трат и экономика запусков.

Траты раньше копились счётчиком «пользователь × сервис × день»: без
номера поиска и без команды, а часть (сводка Claude, Hunter, Apollo,
расшифровка звонков) не писалась вовсе. Теперь каждая трата — строка
журнала с командой, поиском и этапом, а у поиска хранится воронка и
сколько из расходов сгорело.

Revision ID: 20261010_0082
Revises: 20261009_0081
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261010_0082"
down_revision = "20261009_0081"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")


def upgrade() -> None:
    op.create_table(
        "cost_events",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("user_id", sa.String(32), nullable=True),
        sa.Column("team_id", _UUID, nullable=True),
        sa.Column("search_id", _UUID, nullable=True),
        sa.Column("service", sa.String(48), nullable=False),
        sa.Column("stage", sa.String(24), nullable=True),
        sa.Column("units", sa.Float(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
    )
    op.create_index("ix_cost_events_team_created", "cost_events", ["team_id", "created_at"])
    op.create_index("ix_cost_events_search", "cost_events", ["search_id"])
    op.add_column(
        "search_queries",
        sa.Column("economics", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("search_queries", "economics")
    op.drop_index("ix_cost_events_search", table_name="cost_events")
    op.drop_index("ix_cost_events_team_created", table_name="cost_events")
    op.drop_table("cost_events")
