"""user knowledge files (PDF / text uploads for Henry context)

Revision ID: 20260430_0024
Revises: 20260430_0023
Create Date: 2026-04-30 17:00:00

Stores per-user uploads (sales decks, pricelists, brochures) so Henry
can ground scoring + cold-email copy in the user's actual offering.
Content is parsed to plain text on upload — we never re-read the
binary; only ``content_text`` is read at prompt-build time.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260430_0024"
down_revision = "20260430_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_knowledge_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
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
        "ix_user_knowledge_files_user",
        "user_knowledge_files",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_knowledge_files_user", table_name="user_knowledge_files"
    )
    op.drop_table("user_knowledge_files")
