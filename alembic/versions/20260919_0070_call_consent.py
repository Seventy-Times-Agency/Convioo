"""calls.record_consent — client may refuse recording

Revision ID: 20260919_0070
Revises: 20260918_0069
Create Date: 2026-09-19

Каждый звонок начинается с предупреждения о записи; если клиент
против, селз жмёт «Отменить запись» — запись не скачивается, не
расшифровывается и не хранится на платформе.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260919_0070"
down_revision = "20260918_0069"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "calls",
        sa.Column(
            "record_consent",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("calls", "record_consent")
