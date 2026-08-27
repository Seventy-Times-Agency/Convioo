"""telegram_connections table

Revision ID: 20260621_0054
Revises: 20260619_0053
Create Date: 2026-06-21 00:54:00

Adds ``telegram_connections`` — one row per Convioo user who has linked
their Telegram account. Unique on both ``user_id`` and ``chat_id`` so a
user can only connect one Telegram chat, and a Telegram chat can only be
linked to one account.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260621_0054"
down_revision = "20260619_0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "telegram_connections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "linked_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_telegram_connections_user_id"),
        sa.UniqueConstraint("chat_id", name="uq_telegram_connections_chat_id"),
    )
    op.create_index(
        "ix_telegram_connections_user_id", "telegram_connections", ["user_id"]
    )
    op.create_index(
        "ix_telegram_connections_chat_id", "telegram_connections", ["chat_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_telegram_connections_chat_id", table_name="telegram_connections"
    )
    op.drop_index(
        "ix_telegram_connections_user_id", table_name="telegram_connections"
    )
    op.drop_table("telegram_connections")
