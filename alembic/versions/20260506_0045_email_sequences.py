"""add email_sequences table

Revision ID: 20260506_0045
Revises: 20260506_0044
Create Date: 2026-05-06 00:45:00
"""

import sqlalchemy as sa
from alembic import op

revision = "20260506_0045"
down_revision = "20260506_0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_sequences",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("steps", sa.JSON, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_email_sequences_user_id", "email_sequences", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_email_sequences_user_id", table_name="email_sequences")
    op.drop_table("email_sequences")
