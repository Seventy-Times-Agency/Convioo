"""План на человека и аватар профиля

Revision ID: 20261006_0073
Revises: 20261005_0072
Create Date: 2026-10-06

team_memberships.target_calls_day / target_goals_week — объём и результат,
которые РОП или тимлид ставит селзу; users.avatar_url — картинка профиля
(data URL, как логотип брендинга).
"""

import sqlalchemy as sa
from alembic import op

revision = "20261006_0073"
down_revision = "20261005_0072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("team_memberships", sa.Column("target_calls_day", sa.Integer(), nullable=True))
    op.add_column("team_memberships", sa.Column("target_goals_week", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("avatar_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "avatar_url")
    op.drop_column("team_memberships", "target_goals_week")
    op.drop_column("team_memberships", "target_calls_day")
