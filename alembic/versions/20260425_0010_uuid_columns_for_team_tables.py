"""convert team-related CHAR(36) columns to native Postgres UUID

Revision ID: 20260425_0010
Revises: 20260425_0009
Create Date: 2026-04-25 23:00:00

Migrations 0005 and 0008 created the team tables with ``CHAR(36)``
columns for portability with the SQLite test harness. The
SQLAlchemy models, however, declare them with the ``_UUID``
TypeDecorator which under Postgres binds parameters as the native
``UUID`` type. The result: every query that compares a CHAR column
against a UUID-bound parameter blows up with::

    operator does not exist: character = uuid

This converts every CHAR(36) UUID-shaped column to native
``UUID``. FKs that point at them are dropped first and recreated
afterwards because Postgres won't let you change a column type
while a constraint references it. SQLite path is a no-op — the
``_UUID`` decorator already maps the model type to CHAR(36) there.
"""

from __future__ import annotations

from alembic import op


revision = "20260425_0010"
down_revision = "20260425_0009"
branch_labels = None
depends_on = None


_FK_DROPS = [
    ("team_memberships", "team_memberships_team_id_fkey"),
    ("team_invites", "team_invites_team_id_fkey"),
    ("search_queries", "fk_search_queries_team_id"),
]

_COLUMN_CONVERSIONS = [
    ("teams", "id"),
    ("team_memberships", "id"),
    ("team_memberships", "team_id"),
    ("team_invites", "id"),
    ("team_invites", "team_id"),
    ("search_queries", "team_id"),
    ("lead_marks", "id"),
]

_FK_RECREATES = [
    (
        "team_memberships_team_id_fkey",
        "team_memberships",
        "teams",
        ["team_id"],
        ["id"],
    ),
    (
        "team_invites_team_id_fkey",
        "team_invites",
        "teams",
        ["team_id"],
        ["id"],
    ),
    (
        "fk_search_queries_team_id",
        "search_queries",
        "teams",
        ["team_id"],
        ["id"],
    ),
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # SQLite test harness — _UUID decorator already CHARs

    for table, fk in _FK_DROPS:
        op.execute(
            f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{fk}"'
        )

    for table, column in _COLUMN_CONVERSIONS:
        op.execute(
            f'ALTER TABLE "{table}" '
            f'ALTER COLUMN "{column}" TYPE UUID USING "{column}"::uuid'
        )

    for name, table, ref_table, cols, ref_cols in _FK_RECREATES:
        col_list = ", ".join(f'"{c}"' for c in cols)
        ref_col_list = ", ".join(f'"{c}"' for c in ref_cols)
        op.execute(
            f'ALTER TABLE "{table}" '
            f'ADD CONSTRAINT "{name}" '
            f"FOREIGN KEY ({col_list}) "
            f'REFERENCES "{ref_table}" ({ref_col_list}) '
            f"ON DELETE CASCADE"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # Convert UUID back to CHAR(36). The cast is implicit going this
    # direction (uuid → text), but we spell it out for symmetry.
    for table, fk in _FK_DROPS:
        op.execute(
            f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{fk}"'
        )

    for table, column in _COLUMN_CONVERSIONS:
        op.execute(
            f'ALTER TABLE "{table}" '
            f'ALTER COLUMN "{column}" TYPE CHAR(36) USING "{column}"::text'
        )

    for name, table, ref_table, cols, ref_cols in _FK_RECREATES:
        col_list = ", ".join(f'"{c}"' for c in cols)
        ref_col_list = ", ".join(f'"{c}"' for c in ref_cols)
        op.execute(
            f'ALTER TABLE "{table}" '
            f'ADD CONSTRAINT "{name}" '
            f"FOREIGN KEY ({col_list}) "
            f'REFERENCES "{ref_table}" ({ref_col_list}) '
            f"ON DELETE CASCADE"
        )
