"""teams.call_auto_transcribe / call_auto_analyze — автоматика звонков.

Оценка ИИ после каждого звонка теперь по желанию команды (по умолчанию
выключена), расшифровка — включена, как и раньше.

Revision ID: 20261014_0086
Revises: 20261013_0085
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261014_0086"
down_revision = "20261013_0085"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("teams", sa.Column("call_auto_transcribe", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("teams", sa.Column("call_auto_analyze", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("teams", "call_auto_analyze")
    op.drop_column("teams", "call_auto_transcribe")
