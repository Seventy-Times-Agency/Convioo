"""CRM двигается сама: исход звонка ведёт карточку по колонкам.

Раньше звонки шли, а доска стояла — карточка оставалась в «Новый»
до ручного перетаскивания, и канбан показывал вчерашнюю картину.
"""

from __future__ import annotations

from leadgen.adapters.web_api.routes._helpers import (
    _DEFAULT_LEAD_STATUSES,
    LEGACY_LEAD_STATUS_KEYS,
)
from leadgen.adapters.web_api.routes.work import _auto_status_for


def test_goal_moves_to_won():
    assert _auto_status_for("goal", "new") == "won"
    assert _auto_status_for("goal", "contacted") == "won"


def test_refusal_and_wrong_number_move_to_lost():
    assert _auto_status_for("refused", "contacted") == "lost"
    assert _auto_status_for("wrong_number", "new") == "lost"


def test_first_touch_moves_new_to_contacted():
    assert _auto_status_for("callback", "new") == "contacted"
    assert _auto_status_for("thinking", None) == "contacted"
    # Уже в работе — карточку не откатываем.
    assert _auto_status_for("callback", "replied") is None


def test_no_answer_does_not_move_the_card():
    """Недозвон — не касание: карточка остаётся где была."""
    assert _auto_status_for("no_answer", "new") is None


def test_lost_is_in_default_palette_and_legacy_keys():
    """Классификатор ответов давно пишет "lost" — колонка обязана
    существовать, иначе карточки проваливаются в никуда."""
    keys = [k for k, *_ in _DEFAULT_LEAD_STATUSES]
    assert "lost" in keys
    assert "lost" in LEGACY_LEAD_STATUS_KEYS
    # Терминальная: из «Отказа» воронка не продолжается.
    terminal = {k: t for k, _l, _c, _o, t in _DEFAULT_LEAD_STATUSES}
    assert terminal["lost"] is True
