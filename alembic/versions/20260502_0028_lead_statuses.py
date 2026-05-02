"""team-scoped lead status palette

Revision ID: 20260502_0028
Revises: 20260502_0027
Create Date: 2026-05-02 21:00:00

Each team owns its own status palette (replacing the hard-coded
new/contacted/replied/won/archived enum for team-shared CRMs).
Personal-mode leads keep the legacy enum since they don't belong to
a team — the same five status keys ARE seeded into every team so
existing leads stay valid after the migration.

Lead.lead_status remains a free-text column; the column value is
the ``key`` of a row in ``lead_statuses`` for the parent search's
team. A foreign key would be cleaner but would need a migration
back-fill that maps every existing row, which is brittle for now.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260502_0028"
down_revision = "20260502_0027"
branch_labels = None
depends_on = None


_DEFAULT_STATUSES = [
    ("new", "Новый", "slate", 0),
    ("contacted", "Связались", "blue", 1),
    ("replied", "Ответили", "teal", 2),
    ("won", "Сделка", "green", 3),
    ("archived", "Архив", "slate", 99),
]


def upgrade() -> None:
    op.create_table(
        "lead_statuses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=False),
        sa.Column(
            "color",
            sa.String(length=16),
            server_default=sa.text("'slate'"),
            nullable=False,
        ),
        sa.Column(
            "order_index",
            sa.SmallInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "is_terminal",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "team_id", "key", name="uq_lead_statuses_team_key"
        ),
    )
    op.create_index(
        "ix_lead_statuses_team_order",
        "lead_statuses",
        ["team_id", "order_index"],
    )

    # Seed five default statuses into every existing team so existing
    # ``Lead.lead_status`` values stay valid post-migration.
    teams = op.get_bind().execute(sa.text("SELECT id FROM teams")).fetchall()
    for (team_id,) in teams:
        for key, label, color, order_index in _DEFAULT_STATUSES:
            op.get_bind().execute(
                sa.text(
                    "INSERT INTO lead_statuses "
                    "(id, team_id, key, label, color, order_index, is_terminal) "
                    "VALUES (gen_random_uuid(), :team_id, :key, :label, "
                    ":color, :order_index, :is_terminal)"
                ),
                {
                    "team_id": team_id,
                    "key": key,
                    "label": label,
                    "color": color,
                    "order_index": order_index,
                    "is_terminal": key in ("won", "archived"),
                },
            )


def downgrade() -> None:
    op.drop_index(
        "ix_lead_statuses_team_order", table_name="lead_statuses"
    )
    op.drop_table("lead_statuses")
