"""lead custom fields, activity log, tasks

Revision ID: 20260427_0020
Revises: 20260427_0019
Create Date: 2026-04-27 06:30:00

Three new tables that lift the CRM from "list of leads with notes"
to "real CRM": custom fields per lead, an activity timeline so users
can see what changed when, and tasks/reminders attached to a lead.

- ``lead_custom_fields`` — flexible (lead_id, key) → value text. No
  schema lock-in; users can add any key they want from the UI.
- ``lead_activities`` — append-only log: kind ∈ {created, status,
  notes, assigned, mark, custom_field, task}, payload jsonb, who/when.
  Used to render the per-lead timeline + future team activity feed.
- ``lead_tasks`` — due_at + content + done_at. Powers the "поставить
  задачу позвонить завтра" UX and a Today's-tasks widget on dashboard.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260427_0020"
down_revision = "20260427_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lead_custom_fields",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["lead_id"], ["leads.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "lead_id", "user_id", "key",
            name="uq_lead_custom_fields_owner_key",
        ),
    )
    op.create_index(
        "ix_lead_custom_fields_lead_id",
        "lead_custom_fields",
        ["lead_id"],
    )

    op.create_table(
        "lead_activities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["lead_id"], ["leads.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_lead_activities_lead_id",
        "lead_activities",
        ["lead_id"],
    )
    op.create_index(
        "ix_lead_activities_team_id",
        "lead_activities",
        ["team_id"],
    )
    op.create_index(
        "ix_lead_activities_user_id_recent",
        "lead_activities",
        ["user_id", sa.text("created_at DESC")],
    )

    op.create_table(
        "lead_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["lead_id"], ["leads.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_lead_tasks_user_open",
        "lead_tasks",
        ["user_id", "due_at"],
        postgresql_where=sa.text("done_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_lead_tasks_user_open", table_name="lead_tasks")
    op.drop_table("lead_tasks")
    op.drop_index("ix_lead_activities_user_id_recent", table_name="lead_activities")
    op.drop_index("ix_lead_activities_team_id", table_name="lead_activities")
    op.drop_index("ix_lead_activities_lead_id", table_name="lead_activities")
    op.drop_table("lead_activities")
    op.drop_index("ix_lead_custom_fields_lead_id", table_name="lead_custom_fields")
    op.drop_table("lead_custom_fields")
