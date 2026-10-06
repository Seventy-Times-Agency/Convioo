"""search_queries.launch_profile — параметры запуска для поисков в очереди.

Мультигород запускает по поиску на город, а у человека одновременно
может идти только один (uq_user_active_search). Следующие города ждут
в статусе ``queued``; профиль для оценки ИИ (оффер, язык, «кто мы»)
хранится здесь, пока очередь не дойдёт до поиска.

Revision ID: 20261009_0077
Revises: 20261008_0076
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261009_0077"
down_revision = "20261008_0076"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "search_queries",
        sa.Column(
            "launch_profile",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("search_queries", "launch_profile")
