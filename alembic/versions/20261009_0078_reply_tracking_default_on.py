"""Отслеживание ответов в Gmail включено по умолчанию.

Сортировка ответов ИИ («интересно», «встреча», «отписаться») работает
только у тех, у кого включён этот флаг, а по умолчанию он был выключен —
и почти ни у кого не работала. Переключатель в профиле остаётся: кто
выключит, тому не сканируем.

Revision ID: 20261009_0078
Revises: 20261009_0077
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261009_0078"
down_revision = "20261009_0077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE users SET email_reply_tracking_enabled = TRUE")
    with op.batch_alter_table("users") as batch:
        batch.alter_column(
            "email_reply_tracking_enabled",
            existing_type=sa.Boolean(),
            server_default=sa.true(),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.alter_column(
            "email_reply_tracking_enabled",
            existing_type=sa.Boolean(),
            server_default=None,
            existing_nullable=False,
        )
