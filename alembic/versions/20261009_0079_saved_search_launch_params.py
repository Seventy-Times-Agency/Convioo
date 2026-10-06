"""saved_searches.launch_params — полный набор параметров запуска.

Еженедельный повтор хранил только нишу, город и лимит, поэтому терял
каналы, фильтры до оценки, оффер и поиск ЛПР. Теперь сохраняется всё,
с чем человек запускал поиск, и повтор идёт тем же путём, что и кнопка.

Revision ID: 20261009_0079
Revises: 20261009_0078
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261009_0079"
down_revision = "20261009_0078"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "saved_searches",
        sa.Column(
            "launch_params",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("saved_searches", "launch_params")
