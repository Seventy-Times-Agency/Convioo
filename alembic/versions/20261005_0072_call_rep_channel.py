"""calls.rep_channel — на какой дорожке записи говорит сотрудник

Revision ID: 20261005_0072
Revises: 20261003_0071
Create Date: 2026-10-05

В стерео-записи провайдера первая дорожка — сторона, которую он
считает звонящей. При звонке из карточки (callback) это клиент, при
звонке из софтфона — сотрудник. Без этой отметки расшифровка путала,
кто что сказал.
"""

import sqlalchemy as sa
from alembic import op

revision = "20261005_0072"
down_revision = "20261003_0071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("calls", sa.Column("rep_channel", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("calls", "rep_channel")
