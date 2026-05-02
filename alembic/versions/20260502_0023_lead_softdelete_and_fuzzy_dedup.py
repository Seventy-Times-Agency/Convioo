"""lead soft-delete and fuzzy dedup keys

Revision ID: 20260502_0023
Revises: 20260502_0022
Create Date: 2026-05-02 00:30:00

Phase 2 of the search-pipeline rework.

- ``leads.deleted_at`` makes deletion non-destructive: the CRM hides
  the row but keeps it for audit + lets ``UserSeenLead`` reference it.
- ``UserSeenLead`` and ``TeamSeenLead`` gain ``phone_e164`` and
  ``domain_root`` columns. The pipeline now considers a lead a
  duplicate if the place-id ``OR`` the normalized phone ``OR`` the
  domain root has been seen before — same business under a slightly
  different Google listing no longer slips through.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260502_0023"
down_revision = "20260502_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Per-search cap so users can pick 5 / 10 / 20 / 30 / 50 instead
    # of being stuck on the global ``MAX_RESULTS_PER_QUERY`` default.
    op.add_column(
        "search_queries",
        sa.Column("max_results", sa.SmallInteger(), nullable=True),
    )

    op.add_column(
        "leads",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Soft-delete blacklist: rows the user explicitly tagged as
    # "never show again" via ``DELETE /api/v1/leads/{id}?forever=true``.
    # Decoupled from deleted_at because a regular delete is reversible
    # (just clear the column) but a forever-delete must outlive the row.
    op.add_column(
        "leads",
        sa.Column(
            "blacklisted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )

    op.add_column(
        "user_seen_leads",
        sa.Column("phone_e164", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "user_seen_leads",
        sa.Column("domain_root", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_user_seen_leads_phone",
        "user_seen_leads",
        ["user_id", "phone_e164"],
    )
    op.create_index(
        "ix_user_seen_leads_domain",
        "user_seen_leads",
        ["user_id", "domain_root"],
    )

    op.add_column(
        "team_seen_leads",
        sa.Column("phone_e164", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "team_seen_leads",
        sa.Column("domain_root", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_team_seen_leads_phone",
        "team_seen_leads",
        ["team_id", "phone_e164"],
    )
    op.create_index(
        "ix_team_seen_leads_domain",
        "team_seen_leads",
        ["team_id", "domain_root"],
    )


def downgrade() -> None:
    op.drop_index("ix_team_seen_leads_domain", table_name="team_seen_leads")
    op.drop_index("ix_team_seen_leads_phone", table_name="team_seen_leads")
    op.drop_column("team_seen_leads", "domain_root")
    op.drop_column("team_seen_leads", "phone_e164")

    op.drop_index("ix_user_seen_leads_domain", table_name="user_seen_leads")
    op.drop_index("ix_user_seen_leads_phone", table_name="user_seen_leads")
    op.drop_column("user_seen_leads", "domain_root")
    op.drop_column("user_seen_leads", "phone_e164")

    op.drop_column("leads", "blacklisted")
    op.drop_column("leads", "deleted_at")

    op.drop_column("search_queries", "max_results")
