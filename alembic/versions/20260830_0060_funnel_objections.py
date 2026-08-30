"""funnel objections

Revision ID: 20260830_0060
Revises: 20260827_0059
Create Date: 2026-08-30

Экран прозвона (Main/CallActive/CallAfter.dc.html) показывает блок
«ВОЗРАЖЕНИЯ» рядом со скриптом команды: пара «возражение → ответ».
В макете это часть того, что «загружает менеджер», то есть свойство
воронки, а не лида.

Хранится списком объектов [{"objection": "...", "answer": "..."}],
чтобы порядок задавал менеджер. NULL и пустой список равнозначны —
блок в интерфейсе тогда не рисуется.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260830_0060"
down_revision = "20260827_0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "funnels",
        sa.Column(
            "objections",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(
                sa.JSON(), "sqlite"
            ),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("funnels", "objections")
