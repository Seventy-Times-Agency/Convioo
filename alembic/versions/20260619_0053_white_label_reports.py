"""white-label branding on teams + client_reports table

Revision ID: 20260619_0053
Revises: 20260619_0052
Create Date: 2026-06-19 01:00:00

Wave 4 (white-label client reports). Adds agency branding columns to
``teams`` and a ``client_reports`` table holding shareable, revocable
report links over a search's results. All new team columns are nullable,
so the migration is non-blocking on a populated table.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260619_0053"
down_revision = "20260619_0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "teams", sa.Column("brand_name", sa.String(length=120), nullable=True)
    )
    op.add_column("teams", sa.Column("brand_logo", sa.Text(), nullable=True))
    op.add_column(
        "teams", sa.Column("brand_color", sa.String(length=7), nullable=True)
    )

    op.create_table(
        "client_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("search_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column(
            "revoked", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["search_id"], ["search_queries.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token", name="uq_client_reports_token"),
    )
    op.create_index(
        "ix_client_reports_team_id", "client_reports", ["team_id"]
    )
    op.create_index(
        "ix_client_reports_search_id", "client_reports", ["search_id"]
    )
    op.create_index(
        "ix_client_reports_token", "client_reports", ["token"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_client_reports_token", table_name="client_reports")
    op.drop_index("ix_client_reports_search_id", table_name="client_reports")
    op.drop_index("ix_client_reports_team_id", table_name="client_reports")
    op.drop_table("client_reports")
    op.drop_column("teams", "brand_color")
    op.drop_column("teams", "brand_logo")
    op.drop_column("teams", "brand_name")
