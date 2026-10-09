"""call_reviews — сессии общего ИИ-разбора выбранных звонков.

Revision ID: 20261013_0085
Revises: 20261012_0084
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261013_0085"
down_revision = "20261012_0084"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")
_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "call_reviews",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("team_id", _UUID, sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("subject_user_id", sa.BigInteger(), nullable=True),
        sa.Column("call_ids", _JSON, nullable=False),
        sa.Column("focus", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("result", _JSON, nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_call_reviews_team_id", "call_reviews", ["team_id"])


def downgrade() -> None:
    op.drop_index("ix_call_reviews_team_id", table_name="call_reviews")
    op.drop_table("call_reviews")
