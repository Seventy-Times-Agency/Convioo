"""funnels + funnel_steps + lead funnel-execution state

Revision ID: 20260827_0057
Revises: 20260626_0056
Create Date: 2026-08-27

Wave 1: the funnel becomes the central sales entity. A funnel holds
the team's touch path, goal (free text + optional price + on-reach
action), call script and no-answer rule. Leads bind to a funnel and
carry execution state (next step index, due time, no-answer count,
goal-reached stamp) the worker and the call queue run on.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260827_0057"
down_revision = "20260626_0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "funnels",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("goal_name", sa.String(length=200), nullable=False),
        sa.Column("goal_price", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "goal_action",
            sa.String(length=32),
            nullable=False,
            server_default="none",
        ),
        sa.Column("script", sa.Text(), nullable=True),
        sa.Column(
            "no_answer_attempts",
            sa.Integer(),
            nullable=False,
            server_default="3",
        ),
        sa.Column(
            "no_answer_pause_days",
            sa.Integer(),
            nullable=False,
            server_default="14",
        ),
        sa.Column("created_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "name", name="uq_funnels_team_name"),
    )
    op.create_index("ix_funnels_team_id", "funnels", ["team_id"])

    op.create_table(
        "funnel_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("funnel_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column(
            "day_offset", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "auto", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("note", sa.String(length=300), nullable=True),
        sa.Column("extra", postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(
            ["funnel_id"], ["funnels.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["template_id"], ["outreach_templates.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_funnel_steps_funnel_id", "funnel_steps", ["funnel_id"])

    op.add_column(
        "leads",
        sa.Column("funnel_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "leads",
        sa.Column(
            "funnel_step", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "leads",
        sa.Column("next_touch_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "leads",
        sa.Column(
            "no_answer_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "leads",
        sa.Column(
            "goal_reached_at", sa.DateTime(timezone=True), nullable=True
        ),
    )
    op.create_index("ix_leads_funnel_id", "leads", ["funnel_id"])
    op.create_index("ix_leads_next_touch_at", "leads", ["next_touch_at"])
    with op.batch_alter_table("leads") as batch:
        batch.create_foreign_key(
            "fk_leads_funnel_id",
            "funnels",
            ["funnel_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("leads") as batch:
        batch.drop_constraint("fk_leads_funnel_id", type_="foreignkey")
    op.drop_index("ix_leads_next_touch_at", table_name="leads")
    op.drop_index("ix_leads_funnel_id", table_name="leads")
    op.drop_column("leads", "goal_reached_at")
    op.drop_column("leads", "no_answer_count")
    op.drop_column("leads", "next_touch_at")
    op.drop_column("leads", "funnel_step")
    op.drop_column("leads", "funnel_id")
    op.drop_index("ix_funnel_steps_funnel_id", table_name="funnel_steps")
    op.drop_table("funnel_steps")
    op.drop_index("ix_funnels_team_id", table_name="funnels")
    op.drop_table("funnels")
