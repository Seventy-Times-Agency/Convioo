"""record when a user finished the in-app onboarding tour

Revision ID: 20260503_0037
Revises: 20260503_0036
Create Date: 2026-05-03 14:00:00

The 4-step product tour fires on the user's first ``/app`` visit; the
flag below stamps the moment they complete it (or skip it). It is
kept distinct from ``users.onboarded_at`` (which records the profile
gate at registration) because the tour is a UI affordance the user
can replay from Settings while the account-level onboarded_at is a
one-shot identity stamp.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260503_0037"
down_revision = "20260503_0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "onboarding_completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "onboarding_completed_at")
