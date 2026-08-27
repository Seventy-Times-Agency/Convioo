"""user notification preferences + reply-tracker watermark

Revision ID: 20260504_0038
Revises: 20260503_0037
Create Date: 2026-05-04 02:30:00

Stores opt-ins for:

* daily digest emails (the worker cron sends a once-a-day summary)
* Gmail reply tracking (the worker poll fetches replies and logs them
  as ``LeadActivity(kind="email_replied")``)

Both default to False — the worker is a no-op for users who haven't
explicitly turned them on. Two tracker fields keep the polling cheap:
``email_reply_last_history_id`` is the Gmail watermark (so we don't
re-walk the inbox from scratch each tick) and
``email_reply_last_checked_at`` is the last-success timestamp surfaced
in /settings/notifications.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260504_0038"
down_revision = "20260503_0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "daily_digest_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "email_reply_tracking_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "email_reply_last_history_id",
            sa.String(length=64),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "email_reply_last_checked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    # Drop the server defaults — the column DEFAULT was only there so
    # the ALTER TABLE on existing rows didn't fail. New inserts pick up
    # the SQLAlchemy-side default ("False") just fine.
    with op.batch_alter_table("users") as batch:
        batch.alter_column(
            "daily_digest_enabled", server_default=None
        )
        batch.alter_column(
            "email_reply_tracking_enabled", server_default=None
        )


def downgrade() -> None:
    op.drop_column("users", "email_reply_last_checked_at")
    op.drop_column("users", "email_reply_last_history_id")
    op.drop_column("users", "email_reply_tracking_enabled")
    op.drop_column("users", "daily_digest_enabled")
