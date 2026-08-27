"""users.gender — drives Henry's grammatical agreement

Revision ID: 20260427_0018
Revises: 20260427_0017
Create Date: 2026-04-27 04:00:00

Adds an optional ``gender`` column on ``users`` so Henry can address
the user in the right grammatical form (он/она). Values: 'male' |
'female' | 'other'. NULL means "not specified", which the prompt
treats as gender-neutral phrasing.

Not used for any kind of personalisation / filtering / segmenting
beyond pronoun choice — it's a pure UX nicety.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260427_0018"
down_revision = "20260427_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("gender", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "gender")
