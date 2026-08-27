"""user audit logs

Revision ID: 20260427_0021
Revises: 20260427_0020
Create Date: 2026-04-27 15:00:00

Append-only audit table for security-relevant events: sign-in,
profile changes, GDPR data export / account deletion, team
membership transitions. Populated by the web API at the points
where those actions occur; readable by the user from
``/app/profile`` (their own log) — NOT by other users.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260427_0021"
down_revision = "20260427_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=256), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_user_audit_logs_user_id_recent",
        "user_audit_logs",
        ["user_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_audit_logs_user_id_recent", table_name="user_audit_logs"
    )
    op.drop_table("user_audit_logs")
