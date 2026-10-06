"""Team panel: ``GET /teams/{id}/overview`` and per-member targets.

Role rules under test: owner and admin see the whole team, a manager
sees only their own squad, sales can't open the panel at all. Targets:
owner sets for anyone, admin for everyone but the owner, manager only
for sales in their own squad.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from leadgen.db.models import LeadActivity, TeamMembership, TeamSquad

# Переиспользуем сборку команды из теста ролей: те же пять аккаунтов
# и права, панель проверяем поверх них.
pytest_plugins = ["tests.test_team_roles_wave1"]


async def _put_manager_and_sales_in_squad(maker, team_id, ids) -> uuid.UUID:
    squad_id = uuid.uuid4()
    async with maker() as session:
        session.add(TeamSquad(id=squad_id, team_id=team_id, name="A"))
        await session.flush()
        for role in ("manager", "sales"):
            ms = (
                await session.execute(
                    TeamMembership.__table__.select().where(
                        TeamMembership.team_id == team_id,
                        TeamMembership.user_id == ids[role],
                    )
                )
            ).first()
            assert ms is not None
            obj = await session.get(TeamMembership, ms.id)
            obj.squad_id = squad_id
        await session.commit()
    return squad_id


@pytest.mark.asyncio
async def test_overview_scope_by_role(crew, patched_session_factory):
    team_id = crew["team_id"]
    ids = crew["ids"]
    clients = crew["clients"]
    await _put_manager_and_sales_in_squad(patched_session_factory, team_id, ids)

    # A call outcome today for the sales rep: counted on their row.
    async with patched_session_factory() as session:
        session.add(
            LeadActivity(
                id=uuid.uuid4(),
                lead_id=crew["assigned_lead"],
                user_id=ids["sales"],
                team_id=team_id,
                kind="call",
                payload={"outcome": "goal"},
                created_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    r = clients["owner"].get(f"/api/v1/teams/{team_id}/overview")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["people"] == 5
    assert len(body["members"]) == 5
    assert body["calls_today"] == 1
    assert body["goals_7d"] == 1
    sales_row = next(m for m in body["members"] if m["id"] == ids["sales"])
    assert sales_row["calls_today"] == 1
    assert sales_row["talks_today"] == 1
    assert sales_row["leads_count"] == 1
    assert sales_row["can_set_targets"] is True
    owner_row = next(m for m in body["members"] if m["id"] == ids["owner"])
    assert owner_row["can_change_role"] is False

    # Admin: sees everyone, but no controls over the owner.
    r = clients["admin"].get(f"/api/v1/teams/{team_id}/overview")
    assert r.status_code == 200
    owner_row = next(m for m in r.json()["members"] if m["id"] == ids["owner"])
    assert owner_row["can_edit"] is False
    assert owner_row["can_set_targets"] is False
    assert owner_row["can_remove"] is False

    # Manager: only own squad (self + sales), not sales2.
    r = clients["manager"].get(f"/api/v1/teams/{team_id}/overview")
    assert r.status_code == 200
    seen = {m["id"] for m in r.json()["members"]}
    assert seen == {ids["manager"], ids["sales"]}

    # Sales: no panel.
    r = clients["sales"].get(f"/api/v1/teams/{team_id}/overview")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_targets_permissions(crew, patched_session_factory):
    team_id = crew["team_id"]
    ids = crew["ids"]
    clients = crew["clients"]
    await _put_manager_and_sales_in_squad(patched_session_factory, team_id, ids)

    url = f"/api/v1/teams/{team_id}/members/{{uid}}/targets"
    body = {"target_calls_day": 40, "target_goals_week": 5}

    # Manager → own sales: ok; → sales2 (other squad): forbidden.
    r = clients["manager"].patch(url.format(uid=ids["sales"]), json=body)
    assert r.status_code == 200, r.text
    assert r.json()["target_calls_day"] == 40
    r = clients["manager"].patch(url.format(uid=ids["sales2"]), json=body)
    assert r.status_code == 403

    # Admin → owner: forbidden; → manager: ok.
    r = clients["admin"].patch(url.format(uid=ids["owner"]), json=body)
    assert r.status_code == 403
    r = clients["admin"].patch(url.format(uid=ids["manager"]), json=body)
    assert r.status_code == 200

    # Sales: nothing.
    r = clients["sales"].patch(url.format(uid=ids["sales2"]), json=body)
    assert r.status_code == 403

    # Targets show up in the overview; zero clears.
    r = clients["owner"].patch(url.format(uid=ids["sales"]), json={"target_calls_day": 0})
    assert r.status_code == 200
    r = clients["owner"].get(f"/api/v1/teams/{team_id}/overview")
    row = next(m for m in r.json()["members"] if m["id"] == ids["sales"])
    assert row["target_calls_day"] is None
    assert row["target_goals_week"] == 5
