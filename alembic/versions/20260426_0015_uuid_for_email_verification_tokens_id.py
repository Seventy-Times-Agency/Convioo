"""convert email_verification_tokens.id to native Postgres UUID

Revision ID: 20260426_0015
Revises: 20260426_0014
Create Date: 2026-04-26 21:40:00

Migration 0013 created ``email_verification_tokens`` with ``id``
typed as ``CHAR(36)`` for SQLite portability, but the SQLAlchemy
model declares the column with the ``_UUID`` decorator which on
Postgres binds parameters as native UUID. Every UPDATE / SELECT
that filters on ``id`` then fails with::

    operator does not exist: character = uuid

Same fix shape migration 0010 used for the team tables: ALTER the
column type. SQLite path is a no-op.
"""

from __future__ import annotations

from alembic import op


revision = "20260426_0015"
down_revision = "20260426_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        "ALTER TABLE email_verification_tokens "
        "ALTER COLUMN id TYPE UUID USING id::uuid"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        "ALTER TABLE email_verification_tokens "
        "ALTER COLUMN id TYPE CHAR(36) USING id::text"
    )
