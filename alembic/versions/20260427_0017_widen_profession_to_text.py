"""widen users.profession + service_description to TEXT

Revision ID: 20260427_0017
Revises: 20260427_0016
Create Date: 2026-04-27 03:30:00

The profile editor was throwing "value too long for type character
varying(200)" when users saved a long ``service_description``. Two
moving parts contributed:

- ``users.profession`` was created as ``varchar(200)`` in migration
  0002 and never widened, but ``profession`` is now the LLM-polished
  version of ``service_description`` and routinely runs longer than
  200 chars.
- ``users.service_description`` was *intended* to be ``TEXT`` per
  migration 0002, but legacy databases that bootstrapped from an
  older schema can end up with ``varchar(200)``. The ALTER is a no-op
  if the column is already TEXT.

We ALTER both to TEXT so practical input length is governed by the
application schema (Pydantic), not by an arbitrary DB cap nobody
remembers setting.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260427_0017"
down_revision = "20260427_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite stores TEXT for both String() and Text() so there's
        # nothing to change there. Tests use SQLite via _UUID/_JSONB
        # decorators so this path stays a no-op.
        return
    op.alter_column(
        "users",
        "profession",
        existing_type=sa.String(length=200),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.alter_column(
        "users",
        "service_description",
        existing_type=sa.String(length=200),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.alter_column(
        "users",
        "service_description",
        existing_type=sa.Text(),
        type_=sa.String(length=200),
        existing_nullable=True,
    )
    op.alter_column(
        "users",
        "profession",
        existing_type=sa.Text(),
        type_=sa.String(length=200),
        existing_nullable=True,
    )
