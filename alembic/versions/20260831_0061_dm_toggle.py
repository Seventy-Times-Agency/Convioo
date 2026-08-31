"""find_decision_makers toggle on search queries

Revision ID: 20260831_0061
Revises: 20260830_0060
Create Date: 2026-08-31

Поиск ЛПР (OpenCorporates / Proxycurl / разбор сайта) до сих пор шёл
для каждого лида безусловно — платно и молча. Расширенный поиск делает
его явным выбором.

NULL намеренно означает «включён»: так строки, созданные до появления
поля, сохраняют прежнее поведение и не переосмысливаются задним числом.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260831_0061"
down_revision = "20260830_0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "search_queries",
        sa.Column("find_decision_makers", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("search_queries", "find_decision_makers")
