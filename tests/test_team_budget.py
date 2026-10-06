"""Бюджет в $ = лимит токенов: пополнение до бюджета, смена бюджета
посреди месяца, остановка запусков на нуле, права владельца."""

from __future__ import annotations

import pytest

from leadgen.core.services.account import budget
from leadgen.db.models import Team

pytest_plugins = ["tests.test_team_roles_wave1"]


def test_allowance_uses_lead_cost():
    price = budget.token_price_usd()
    assert price > 0
    assert budget.allowance(None) == 0
    assert budget.allowance(price * 100) == 100


@pytest.mark.asyncio
async def test_budget_refills_and_limits(crew, patched_session_factory):
    team_id = crew["team_id"]
    owner = crew["clients"]["owner"]
    price = budget.token_price_usd()

    # Команда ушла в минус до появления бюджета.
    async with patched_session_factory() as session:
        team = await session.get(Team, team_id)
        team.token_balance = -40
        await session.commit()

    r = owner.patch(f"/api/v1/teams/{team_id}/money", json={"budget_usd": round(price * 200, 4), "stop_at_zero": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["allowance"] == 200
    assert body["balance"] == 200  # минус закрыт, баланс = бюджету
    assert body["stop_at_zero"] is True

    # Повторное чтение в том же месяце не пополняет второй раз.
    assert owner.get(f"/api/v1/teams/{team_id}/money").json()["balance"] == 200

    # Бюджет увеличили посреди месяца — добавляется разница.
    r = owner.patch(f"/api/v1/teams/{team_id}/money", json={"budget_usd": round(price * 300, 4)})
    assert r.json()["balance"] == 300

    # Ручное начисление.
    r = owner.post(f"/api/v1/teams/{team_id}/money/grant", json={"tokens": 25})
    assert r.json()["balance"] == 325

    # Остановка на нуле: запуск дороже баланса — 402.
    async with patched_session_factory() as session:
        team = await session.get(Team, team_id)
        team.token_balance = 5
        await session.commit()
    r = owner.post(
        "/api/v1/searches",
        json={"niche": "dentists", "region": "Lviv", "team_id": str(team_id), "limit": 50},
    )
    assert r.status_code == 402, r.text

    # Не владелец — 403.
    assert crew["clients"]["admin"].get(f"/api/v1/teams/{team_id}/money").status_code == 403


@pytest.mark.asyncio
async def test_connections_overview(crew):
    team_id = crew["team_id"]
    r = crew["clients"]["admin"].get(f"/api/v1/teams/{team_id}/connections")
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["members"]) == 5
    assert all(m["telegram"] is False for m in body["members"])
    assert crew["clients"]["sales"].get(f"/api/v1/teams/{team_id}/connections").status_code == 403
