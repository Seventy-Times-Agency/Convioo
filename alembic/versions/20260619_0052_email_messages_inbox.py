"""email_messages table for the unified Inbox

Revision ID: 20260619_0052
Revises: 20260616_0051
Create Date: 2026-06-19 00:00:00

Wave 3 (Inbox/unibox). Stores synced inbound/outbound messages from
connected Gmail/Outlook mailboxes. Threads are derived by grouping on
(user_id, provider, provider_thread_id); the unique constraint on the
provider message id keeps the sync idempotent.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260619_0052"
down_revision = "20260616_0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("account_email", sa.String(length=320), nullable=True),
        sa.Column(
            "provider_thread_id", sa.String(length=256), nullable=False
        ),
        sa.Column(
            "provider_message_id", sa.String(length=256), nullable=False
        ),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("from_email", sa.String(length=320), nullable=True),
        sa.Column("to_email", sa.String(length=320), nullable=True),
        sa.Column("subject", sa.String(length=998), nullable=True),
        sa.Column("snippet", sa.String(length=512), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column(
            "message_sent_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "is_read", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "headers",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["lead_id"], ["leads.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "provider",
            "provider_message_id",
            name="uq_email_messages_provider_msg",
        ),
    )
    op.create_index(
        "ix_email_messages_user_id", "email_messages", ["user_id"]
    )
    op.create_index(
        "ix_email_messages_provider_thread_id",
        "email_messages",
        ["provider_thread_id"],
    )
    op.create_index(
        "ix_email_messages_lead_id", "email_messages", ["lead_id"]
    )
    op.create_index(
        "ix_email_messages_message_sent_at",
        "email_messages",
        ["message_sent_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_email_messages_message_sent_at", table_name="email_messages"
    )
    op.drop_index("ix_email_messages_lead_id", table_name="email_messages")
    op.drop_index(
        "ix_email_messages_provider_thread_id", table_name="email_messages"
    )
    op.drop_index("ix_email_messages_user_id", table_name="email_messages")
    op.drop_table("email_messages")
