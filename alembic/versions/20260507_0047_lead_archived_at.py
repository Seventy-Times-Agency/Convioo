"""add archived_at to leads

Revision ID: 20260507_0047
Revises: 20260506_0046
Create Date: 2026-05-07 03:00:00

Soft-archive separate from ``deleted_at``: archive is a user-facing
"not interested, hide for good but keep restorable" state, deletion
is a permanent CRM removal. Archive also write-throughs into
``user_seen_leads`` / ``team_seen_leads`` so the same lead never
shows up in a future search — even after the row is restored.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260507_0047"
down_revision = "20260506_0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Partial index — most leads are never archived, so a filtered
    # index keeps the CRM list query fast without indexing the
    # NULL majority.
    op.create_index(
        "ix_leads_archived_at",
        "leads",
        ["archived_at"],
        postgresql_where=sa.text("archived_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_leads_archived_at", table_name="leads")
    op.drop_column("leads", "archived_at")
