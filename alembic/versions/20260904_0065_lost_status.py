"""backfill the "lost" lead status

Revision ID: 20260904_0065
Revises: 20260903_0064
Create Date: 2026-09-04

Классификатор ответов давно пишет lead_status="lost" (не интересно,
отписка), а в палитре команд такой колонки не было — карточки
проваливались в несуществующий статус и доска врала. Теперь «Отказ»
входит в стандартную палитру, а исход «Отказ/Неверный номер» в
прозвоне двигает карточку туда же. Существующим командам колонка
доливается идемпотентно; ярлык можно переименовать.
"""

import uuid

import sqlalchemy as sa
from alembic import op

revision = "20260904_0065"
down_revision = "20260903_0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    teams = conn.execute(sa.text("SELECT id FROM teams")).scalars().all()
    for team_id in teams:
        exists = conn.execute(
            sa.text(
                "SELECT 1 FROM lead_statuses "
                "WHERE team_id = :t AND key = 'lost'"
            ),
            {"t": str(team_id) if not isinstance(team_id, str) else team_id},
        ).first()
        if exists:
            continue
        conn.execute(
            sa.text(
                "INSERT INTO lead_statuses "
                "(id, team_id, key, label, color, order_index, is_terminal) "
                "VALUES (:id, :t, 'lost', :label, 'red', 4, :term)"
            ),
            {
                "id": str(uuid.uuid4()),
                "t": str(team_id) if not isinstance(team_id, str) else team_id,
                "label": "Отказ",
                "term": True,
            },
        )


def downgrade() -> None:
    # Колонку с живыми карточками назад не выпиливаем.
    pass
