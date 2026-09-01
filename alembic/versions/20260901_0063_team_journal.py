"""team action journal

Revision ID: 20260901_0063
Revises: 20260831_0062
Create Date: 2026-09-01

Неизменяемая лента действий команды: распределения пакетов, правки
воронок, приглашения, смены потолка, завершённые добычи, экспорты.
Текст не хранится — хранится kind + payload, фразу собирает интерфейс
на языке пользователя. Имя и роль актора снимаются в момент записи,
чтобы журнал читался и после ухода людей из команды.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260901_0063"
down_revision = "20260831_0062"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")
_JSONB = postgresql.JSONB(astext_type=sa.Text()).with_variant(
    sa.JSON(), "sqlite"
)


def upgrade() -> None:
    op.create_table(
        "team_action_logs",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column(
            "team_id",
            _UUID,
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "actor_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("actor_name", sa.String(120), nullable=True),
        sa.Column("actor_role", sa.String(16), nullable=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("payload", _JSONB, nullable=True),
        sa.Column("object_label", sa.String(160), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ix_team_action_logs_team_id", "team_action_logs", ["team_id"]
    )
    op.create_index(
        "ix_team_action_logs_actor_id", "team_action_logs", ["actor_id"]
    )
    op.create_index(
        "ix_team_action_logs_kind", "team_action_logs", ["kind"]
    )
    op.create_index(
        "ix_team_action_logs_created_at", "team_action_logs", ["created_at"]
    )


def downgrade() -> None:
    op.drop_table("team_action_logs")
