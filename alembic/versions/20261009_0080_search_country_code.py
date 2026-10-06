"""search_queries.country_code — страна города из справочника.

Регион для Google брался из первого выбранного языка: украинский язык
плюс Варшава давали уклон в Украину. Теперь страна приходит вместе с
городом и задаёт регион поиска.

Revision ID: 20261009_0080
Revises: 20261009_0079
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261009_0080"
down_revision = "20261009_0079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "search_queries", sa.Column("country_code", sa.String(2), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("search_queries", "country_code")
