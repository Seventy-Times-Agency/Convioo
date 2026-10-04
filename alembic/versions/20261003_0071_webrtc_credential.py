"""users.webrtc_credential_id — телефонный credential Telnyx на человека

Revision ID: 20261003_0071
Revises: 20260919_0070
Create Date: 2026-10-03

Звонок из браузера идёт под персональным credential провайдера:
создаём его один раз при первом запросе токена и дальше выдаём по
нему JWT. Без колонки пришлось бы заводить новый credential на каждый
вход и плодить их у провайдера.
"""

import sqlalchemy as sa
from alembic import op

revision = "20261003_0071"
down_revision = "20260919_0070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("webrtc_credential_id", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "webrtc_credential_id")
