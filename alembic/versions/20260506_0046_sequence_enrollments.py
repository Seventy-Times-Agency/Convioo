"""add sequence_enrollments table

Revision ID: 20260506_0046
Revises: 20260506_0045
Create Date: 2026-05-06 00:46:00
"""

import sqlalchemy as sa
from alembic import op

revision = "20260506_0046"
down_revision = "20260506_0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sequence_enrollments",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "sequence_id",
            sa.UUID(),
            sa.ForeignKey("email_sequences.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "lead_id",
            sa.UUID(),
            sa.ForeignKey("leads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("current_step", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="active"
        ),
        sa.Column("next_send_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "enrolled_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_seq_enrollments_user", "sequence_enrollments", ["user_id"]
    )
    op.create_index(
        "ix_seq_enrollments_next_send",
        "sequence_enrollments",
        ["next_send_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_seq_enrollments_next_send", table_name="sequence_enrollments"
    )
    op.drop_index("ix_seq_enrollments_user", table_name="sequence_enrollments")
    op.drop_table("sequence_enrollments")
