"""team auto-distribute flag

Revision ID: 20260912_0068
Revises: 20260908_0067
Create Date: 2026-09-12

Автораспределение базы: при заходе руководителя в Базу сырьё само
честно раздаётся селзам (змейкой по скору — поровну и по количеству,
и по качеству). Флаг на команде, по умолчанию выключен.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260912_0068"
down_revision = "20260908_0067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "teams",
        sa.Column(
            "auto_distribute",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("teams", "auto_distribute")
