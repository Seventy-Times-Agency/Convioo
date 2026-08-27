"""real email-based auth: passwords, email column, verification tokens

Revision ID: 20260426_0013
Revises: 20260425_0012
Create Date: 2026-04-26 09:00:00

Migration to a proper email + password registration. Adds:

- ``users.email`` (citext-style: lowercased on the application side,
  unique partial index over non-null values to keep Telegram rows —
  which never have an email — out of the constraint).
- ``users.password_hash`` — argon2-cffi output, nullable for legacy
  Telegram rows.
- ``users.email_verified_at`` — null until the user clicks the link.
- ``email_verification_tokens`` — short-lived tokens we issue on
  signup / resend; ``kind`` discriminator leaves room for password
  reset later without a second table.

Wipes the existing ``id < 0`` rows (the old web demo users that
authenticated by name only). The CLAUDE.md note explicitly OKs this:
the demo accounts have no email, no password, no real workspace —
they have to re-register. Telegram rows (id > 0) are untouched.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260426_0013"
down_revision = "20260425_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Wipe legacy name-only web users — cascades clean every search,
    # team, lead and mark they ever owned. Telegram users untouched.
    op.execute("DELETE FROM users WHERE id < 0")

    op.add_column("users", sa.Column("email", sa.String(length=255), nullable=True))
    op.add_column(
        "users", sa.Column("password_hash", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Unique only over non-null emails so Telegram rows (NULL email)
    # don't fight each other for the constraint slot.
    op.create_index(
        "ix_users_email_unique",
        "users",
        ["email"],
        unique=True,
        postgresql_where=sa.text("email IS NOT NULL"),
    )

    op.create_table(
        "email_verification_tokens",
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "kind",
            sa.String(length=16),
            server_default=sa.text("'verify'"),
            nullable=False,
        ),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token", name="uq_email_verification_tokens_token"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_email_verification_tokens_user_id",
        "email_verification_tokens",
        ["user_id"],
        unique=False,
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            'ALTER TABLE email_verification_tokens DROP CONSTRAINT IF EXISTS '
            '"email_verification_tokens_user_id_fkey"'
        )
        # No type alter needed for user_id (BigInt) — keep here for symmetry
        # with the rest of the team-side migrations.
        op.execute(
            'ALTER TABLE email_verification_tokens ADD CONSTRAINT '
            '"email_verification_tokens_user_id_fkey" '
            'FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE'
        )


def downgrade() -> None:
    op.drop_index(
        "ix_email_verification_tokens_user_id",
        table_name="email_verification_tokens",
    )
    op.drop_table("email_verification_tokens")
    op.drop_index("ix_users_email_unique", table_name="users")
    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "email")
