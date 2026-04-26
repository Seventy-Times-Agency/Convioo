"""pending_email column on email_verification_tokens

Revision ID: 20260426_0014
Revises: 20260426_0013
Create Date: 2026-04-26 17:00:00

When a signed-in user wants to change their email, we issue a
``kind='change_email'`` verification token and stash the proposed
new address on the token row. Only after the user clicks the link
and we verify the token does ``users.email`` get rewritten to that
``pending_email``. Until then the original email keeps working —
no race window where an account is half-changed.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260426_0014"
down_revision = "20260426_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "email_verification_tokens",
        sa.Column("pending_email", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("email_verification_tokens", "pending_email")
