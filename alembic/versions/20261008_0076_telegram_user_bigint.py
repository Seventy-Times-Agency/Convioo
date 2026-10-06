"""telegram_connections.user_id → BIGINT.

``users.id`` у нас 64-битный (id генерируются большими), а здесь колонка
была INTEGER — запрос статуса Telegram падал с «value out of int32
range» и в профиле пустела карточка Telegram.

Revision ID: 20261008_0076
Revises: 20261008_0075
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261008_0076"
down_revision = "20261008_0075"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("telegram_connections") as batch:
        batch.alter_column("user_id", type_=sa.BigInteger(), existing_type=sa.Integer(), existing_nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("telegram_connections") as batch:
        batch.alter_column("user_id", type_=sa.Integer(), existing_type=sa.BigInteger(), existing_nullable=False)
