"""add users.notify_daily_digest preference

Revision ID: 20260503_0038
Revises: 20260503_0037
Create Date: 2026-05-03 15:00:00

Opt-in morning digest email (9:00 UTC) listing new leads, hot leads
(score >= 80), and replied leads for the past 24 hours. Defaults to
False so existing users are not spammed on deploy.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260503_0038"
down_revision = "20260503_0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "notify_daily_digest",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "notify_daily_digest")
