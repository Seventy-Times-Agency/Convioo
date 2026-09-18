"""telephony: calls table + member phone extension

Revision ID: 20260918_0069
Revises: 20260912_0068
Create Date: 2026-09-18

Звонки через провайдера телефонии (первый — Ringostat): строка на
разговор с длительностью, ссылкой на запись, расшифровкой и разбором
Claude. У участника команды — номер/SIP, на который звонок идёт
первым (схема «сначала селз, потом клиент»).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260918_0069"
down_revision = "20260912_0068"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")
_JSON = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "calls",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column(
            "team_id", _UUID,
            sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column(
            "lead_id", _UUID,
            sa.ForeignKey("leads.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column(
            "user_id", sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_call_id", sa.String(128), nullable=True),
        sa.Column(
            "direction", sa.String(8), nullable=False, server_default="out"
        ),
        sa.Column("to_number", sa.String(32), nullable=True),
        sa.Column(
            "state", sa.String(16), nullable=False, server_default="dialing"
        ),
        sa.Column("duration_sec", sa.Integer(), nullable=True),
        sa.Column("talk_sec", sa.Integer(), nullable=True),
        sa.Column("recording_url", sa.Text(), nullable=True),
        sa.Column("transcript", _JSON, nullable=True),
        sa.Column("analysis", _JSON, nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_calls_team_id", "calls", ["team_id"])
    op.create_index("ix_calls_lead_id", "calls", ["lead_id"])
    op.create_index("ix_calls_to_number", "calls", ["to_number"])
    op.create_index("ix_calls_provider_call_id", "calls", ["provider_call_id"])
    op.add_column(
        "team_memberships",
        sa.Column("phone_extension", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("team_memberships", "phone_extension")
    op.drop_table("calls")
