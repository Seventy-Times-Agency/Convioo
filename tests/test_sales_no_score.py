"""Селз не видит оценку лида: ни в списке, ни в карточке, ни в очереди."""

from __future__ import annotations

import pytest

from leadgen.db.models import Lead

pytest_plugins = ["tests.test_team_roles_wave1"]


@pytest.mark.asyncio
async def test_sales_never_gets_score(crew, patched_session_factory):
    async with patched_session_factory() as session:
        lead = await session.get(Lead, crew["assigned_lead"])
        lead.score_ai = 91
        lead.score_components = {"rating": 30}
        await session.commit()

    team = str(crew["team_id"])
    sales = crew["clients"]["sales"]
    r = sales.get("/api/v1/leads", params={"team_id": team})
    row = next(x for x in r.json()["leads"] if x["id"] == str(crew["assigned_lead"]))
    assert row["score_ai"] is None and row["score_components"] is None

    r = sales.get(f"/api/v1/leads/{crew['assigned_lead']}")
    assert r.status_code == 200, r.text
    assert r.json()["score_ai"] is None

    r = sales.get("/api/v1/work/queue", params={"team_id": team})
    items = [q for b in ("callbacks", "hot", "rest", "later") for q in r.json()[b]]
    assert items and all(q["score"] is None for q in items)

    # Тимлид оценку видит.
    r = crew["clients"]["manager"].get(f"/api/v1/leads/{crew['assigned_lead']}")
    assert r.json()["score_ai"] == 91
