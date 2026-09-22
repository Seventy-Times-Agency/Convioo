"""backfill full default status palettes

Revision ID: 20260908_0067
Revises: 20260904_0066
Create Date: 2026-09-08

Миграция 0065 долила «Отказ» в том числе командам с ПУСТОЙ палитрой —
их доска рисовалась из запасного набора интерфейса, а после доливки
стала «настоящей» палитрой из одной колонки. Здесь каждой команде
идемпотентно доливаются все недостающие стандартные колонки — доска
снова показывает полный путь Новый → … → Сделка / Отказ / Архив.
"""

import uuid

import sqlalchemy as sa
from alembic import op

revision = "20260908_0067"
down_revision = "20260904_0066"
branch_labels = None
depends_on = None

_DEFAULTS = (
    ("new", "Новый", "slate", 0, False),
    ("contacted", "Связались", "blue", 1, False),
    ("replied", "Ответили", "teal", 2, False),
    ("won", "Сделка", "green", 3, True),
    ("lost", "Отказ", "red", 4, True),
    ("archived", "Архив", "slate", 99, True),
)


def upgrade() -> None:
    conn = op.get_bind()
    teams = conn.execute(sa.text("SELECT id FROM teams")).scalars().all()
    for team_id in teams:
        tid = str(team_id) if not isinstance(team_id, str) else team_id
        existing = set(
            conn.execute(
                sa.text(
                    "SELECT key FROM lead_statuses WHERE team_id = :t"
                ),
                {"t": tid},
            ).scalars()
        )
        for key, label, color, order_index, terminal in _DEFAULTS:
            if key in existing:
                continue
            conn.execute(
                sa.text(
                    "INSERT INTO lead_statuses "
                    "(id, team_id, key, label, color, order_index, "
                    "is_terminal) VALUES "
                    "(:id, :t, :k, :l, :c, :o, :term)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "t": tid,
                    "k": key,
                    "l": label,
                    "c": color,
                    "o": order_index,
                    "term": terminal,
                },
            )


def downgrade() -> None:
    pass
