"""user-issued API keys for the public API

Revision ID: 20260502_0029
Revises: 20260502_0028
Create Date: 2026-05-02 22:00:00

Long-lived bearer tokens scoped to a single user. Stored as SHA-256
hashes; the plaintext is shown to the user once at creation and
never persisted. Companion to the cookie session: the same FastAPI
``get_current_user`` dependency accepts either, so any endpoint a
human can call from /app a script can call with a Bearer token.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260502_0029"
down_revision = "20260502_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("token_preview", sa.String(length=16), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_used_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "revoked_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "token_hash", name="uq_user_api_keys_token_hash"
        ),
    )
    op.create_index(
        "ix_user_api_keys_user_active",
        "user_api_keys",
        ["user_id", "revoked_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_api_keys_user_active", table_name="user_api_keys"
    )
    op.drop_table("user_api_keys")
