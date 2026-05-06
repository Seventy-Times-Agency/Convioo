"""add score_components to leads

Revision ID: 20260506_0042
Revises: 20260506_0040
Create Date: 2026-05-06 00:42:00

Stores per-component breakdown of the AI score so the UI can render
a progress bar for each scoring dimension.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260506_0042"
down_revision = "20260506_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("score_components", sa.JSON, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("leads", "score_components")
