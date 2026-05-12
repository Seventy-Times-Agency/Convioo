"""indexes on hot foreign keys + User.email unique + JSON to JSONB

Revision ID: 20260512_0049
Revises: 20260507_0048
Create Date: 2026-05-12 09:00:00

Three load-bearing changes the audit flagged as P0:

1. Add btree indexes on every foreign key column that's used in hot
   filter / cascade paths but did not have ``index=True`` on the model.
   Without these, every JOIN / DELETE-CASCADE / ``WHERE user_id = X``
   degrades to a sequential scan once the parent table grows.

2. Backfill ``users.email`` uniqueness. The model accepted duplicate
   emails (race on signup) and full-scanned the table on every login
   lookup. We lowercase + dedupe in-place (keeping the earliest user),
   then add a unique partial index on ``LOWER(email)``.

3. Promote three JSON columns to JSONB (``leads.score_components``,
   ``leads.rating_snapshots``, ``users.icp_profile``). The plain JSON
   type prevents indexed contains / path queries and is slower to
   parse than the binary form.

All Postgres-specific. On SQLite (test fixture) the migration is a
no-op — the application code already adapts via the ``_JSONB`` /
``_UUID`` TypeDecorators, and SQLite doesn't enforce FK indexes.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260512_0049"
down_revision = "20260507_0048"
branch_labels = None
depends_on = None


# (table, column[, index_name])
_FK_INDEXES: list[tuple[str, str]] = [
    ("user_sessions", "user_id"),
    ("user_api_keys", "user_id"),
    ("oauth_credentials", "user_id"),
    ("user_integration_credentials", "user_id"),
    ("webhooks", "user_id"),
    ("referrals", "user_id"),
    ("team_memberships", "user_id"),
    ("team_memberships", "team_id"),
    ("team_invites", "team_id"),
    ("team_invites", "created_by_user_id"),
    ("team_invites", "accepted_by_user_id"),
    ("lead_marks", "user_id"),
    ("lead_marks", "lead_id"),
    ("lead_custom_fields", "lead_id"),
    ("lead_custom_fields", "user_id"),
    ("lead_tasks", "lead_id"),
    ("lead_tasks", "user_id"),
    ("lead_tasks", "team_id"),
    ("lead_tags", "user_id"),
    ("lead_tags", "team_id"),
    ("lead_tag_assignments", "lead_id"),
    ("lead_tag_assignments", "lead_tag_id"),
    ("lead_activities", "lead_id"),
    ("lead_activities", "user_id"),
    ("lead_activities", "team_id"),
    ("lead_statuses", "team_id"),
    ("sequence_enrollments", "user_id"),
    ("sequence_enrollments", "email_sequence_id"),
    ("sequence_enrollments", "lead_id"),
    ("email_sequences", "user_id"),
    ("email_sequences", "team_id"),
    ("search_queries", "team_id"),
    ("saved_searches", "user_id"),
    ("saved_searches", "team_id"),
    ("leads", "query_id"),
]


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        return

    # 1. FK indexes. CREATE INDEX (non-CONCURRENTLY) is enough on first
    # deploy — tables are small. For larger tables operators can switch
    # to CONCURRENTLY manually before applying.
    for table, column in _FK_INDEXES:
        index_name = f"ix_{table}_{column}"
        op.execute(
            sa.text(
                f'CREATE INDEX IF NOT EXISTS "{index_name}" '
                f'ON "{table}" ("{column}")'
            )
        )

    # 2. users.email — dedupe before adding uniqueness so an existing
    # collision doesn't make the migration fail. The newer row wins
    # (smaller surface area: just clear email/password_hash/recovery so
    # they can re-register), keeping the oldest signup intact.
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT
                    id,
                    LOWER(email) AS email_lc,
                    ROW_NUMBER() OVER (
                        PARTITION BY LOWER(email)
                        ORDER BY created_at ASC, id ASC
                    ) AS rn
                FROM users
                WHERE email IS NOT NULL
            )
            UPDATE users
            SET email = NULL,
                password_hash = NULL,
                recovery_email = NULL
            FROM ranked
            WHERE users.id = ranked.id
              AND ranked.rn > 1
            """
        )
    )
    op.execute(
        sa.text(
            'CREATE UNIQUE INDEX IF NOT EXISTS "uq_users_email_lower" '
            'ON "users" (LOWER(email)) WHERE email IS NOT NULL'
        )
    )

    # 3. JSON → JSONB. ``USING column::jsonb`` is safe because the JSON
    # text on disk is already valid JSON.
    op.execute(
        sa.text(
            'ALTER TABLE "leads" '
            'ALTER COLUMN "score_components" TYPE JSONB '
            'USING "score_components"::jsonb'
        )
    )
    op.execute(
        sa.text(
            'ALTER TABLE "leads" '
            'ALTER COLUMN "rating_snapshots" TYPE JSONB '
            'USING "rating_snapshots"::jsonb'
        )
    )
    op.execute(
        sa.text(
            'ALTER TABLE "users" '
            'ALTER COLUMN "icp_profile" TYPE JSONB '
            'USING "icp_profile"::jsonb'
        )
    )


def downgrade() -> None:
    if not _is_postgres():
        return

    op.execute(
        sa.text(
            'ALTER TABLE "users" '
            'ALTER COLUMN "icp_profile" TYPE JSON '
            'USING "icp_profile"::json'
        )
    )
    op.execute(
        sa.text(
            'ALTER TABLE "leads" '
            'ALTER COLUMN "rating_snapshots" TYPE JSON '
            'USING "rating_snapshots"::json'
        )
    )
    op.execute(
        sa.text(
            'ALTER TABLE "leads" '
            'ALTER COLUMN "score_components" TYPE JSON '
            'USING "score_components"::json'
        )
    )

    op.execute(
        sa.text('DROP INDEX IF EXISTS "uq_users_email_lower"')
    )
    # Note: the dedupe in upgrade() is irreversible (it nulled out
    # losers' emails). Downgrade does not try to undo that — it only
    # removes the uniqueness constraint.

    for table, column in reversed(_FK_INDEXES):
        index_name = f"ix_{table}_{column}"
        op.execute(sa.text(f'DROP INDEX IF EXISTS "{index_name}"'))
