"""token ledger + team balance

Revision ID: 20260831_0062
Revises: 20260831_0061
Create Date: 2026-08-31

Токены — валюта, в которой команда видит стоимость работы: один
базовый лид равен одному токену. Доллары в cost_control остаются
внутренней себестоимостью для админки платформы; слои намеренно
разные.

Журнал, а не одно число: число отвечает только на «сколько осталось»,
а спрашивать будут «куда ушло», «вернулось ли за упавший поиск»,
«сколько докупили». teams.token_balance — кэш суммы журнала,
обновляется в той же транзакции, что и строка.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260831_0062"
down_revision = "20260831_0061"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")


def upgrade() -> None:
    op.add_column(
        "teams",
        sa.Column(
            "token_balance",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_table(
        "token_ledger",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column(
            "team_id",
            _UUID,
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column(
            "search_id",
            _UUID,
            sa.ForeignKey("search_queries.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_token_ledger_team_id", "token_ledger", ["team_id"])
    op.create_index("ix_token_ledger_kind", "token_ledger", ["kind"])
    op.create_index("ix_token_ledger_search_id", "token_ledger", ["search_id"])
    op.create_index(
        "ix_token_ledger_created_at", "token_ledger", ["created_at"]
    )


def downgrade() -> None:
    op.drop_table("token_ledger")
    op.drop_column("teams", "token_balance")
