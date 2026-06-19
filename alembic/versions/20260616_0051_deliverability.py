"""deliverability — lead contact_email/verification + email_daily_sends

Revision ID: 20260616_0051
Revises: 20260512_0050
Create Date: 2026-06-16 00:00:00

Wave 2 (deliverability). Adds the chosen outreach address + verification
verdict to ``leads`` (so the send path can refuse dead addresses), and a
per-day outbound counter table that powers warmup + anti-spam caps.

All new columns are nullable / have safe defaults, so the migration is
non-blocking on a populated table.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260616_0051"
down_revision = "20260512_0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "leads", sa.Column("contact_email", sa.String(length=320), nullable=True)
    )
    op.add_column(
        "leads", sa.Column("email_status", sa.String(length=16), nullable=True)
    )
    op.add_column(
        "leads",
        sa.Column(
            "email_checked_at", sa.DateTime(timezone=True), nullable=True
        ),
    )

    op.create_table(
        "email_daily_sends",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("send_date", sa.Date(), nullable=False),
        sa.Column(
            "sent_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "send_date", name="uq_email_daily_sends_user_date"
        ),
    )
    op.create_index(
        "ix_email_daily_sends_user_id",
        "email_daily_sends",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_email_daily_sends_user_id", table_name="email_daily_sends"
    )
    op.drop_table("email_daily_sends")
    op.drop_column("leads", "email_checked_at")
    op.drop_column("leads", "email_status")
    op.drop_column("leads", "contact_email")
