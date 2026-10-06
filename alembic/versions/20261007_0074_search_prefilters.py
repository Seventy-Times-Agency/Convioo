"""search_queries.prefilters — фильтры до оценки (сайт, рейтинг, отзывы).

Revision ID: 20261007_0074
Revises: 20261006_0073
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261007_0074"
down_revision = "20261006_0073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("search_queries", sa.Column("prefilters", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("search_queries", "prefilters")
