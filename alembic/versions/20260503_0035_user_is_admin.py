"""flag a small set of users as platform admins

Revision ID: 20260503_0035
Revises: 20260503_0034
Create Date: 2026-05-03 11:30:00

A boolean on ``users``. Defaults to false; a row is promoted via
direct SQL on Railway by the founder so we don't have to ship an
"invite an admin" UI on day one. The flag gates ``/api/v1/admin/*``
endpoints and the ``/app/admin`` route on the frontend.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260503_0035"
down_revision = "20260503_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_admin",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "is_admin")
