"""add users.last_name for the web sign-up form

Revision ID: 20260425_0007
Revises: 20260424_0006
Create Date: 2026-04-25 12:00:00

Real registration now captures both first_name and last_name. The
column is nullable to keep existing Telegram-origin rows happy
(Telegram doesn't always supply a last name).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260425_0007"
down_revision = "20260424_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("last_name", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "last_name")
