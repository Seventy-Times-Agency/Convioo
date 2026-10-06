"""Аналитика продаж: числа, воронка, исходы, выводы — на сидированных
активностях поверх команды из теста ролей."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from leadgen.db.models import Call, Lead, LeadActivity, TeamMembership

pytest_plugins = ["tests.test_team_roles_wave1"]


@pytest.mark.asyncio
async def test_sales_analytics_shape_and_rules(crew, patched_session_factory):
    team_id = crew["team_id"]
    ids = crew["ids"]
    clients = crew["clients"]
    now = datetime.now(timezone.utc)

    async with patched_session_factory() as session:
        # План у селза: 10 наборов в день → в месяце ~210; сделал 4.
        ms = (
            await session.execute(
                TeamMembership.__table__.select().where(
                    TeamMembership.team_id == team_id,
                    TeamMembership.user_id == ids["sales"],
                )
            )
        ).first()
        obj = await session.get(TeamMembership, ms.id)
        obj.target_calls_day = 10
        obj.target_goals_week = 1
        lead = await session.get(Lead, crew["assigned_lead"])
        lead.score_ai = 90
        lead.next_touch_at = now - timedelta(days=1)  # просроченный перезвон
        for i, outcome in enumerate(["goal", "callback", "no_answer", "refused"]):
            session.add(
                LeadActivity(
                    id=uuid.uuid4(),
                    lead_id=crew["assigned_lead"],
                    user_id=ids["sales"],
                    team_id=team_id,
                    kind="call",
                    payload={"outcome": outcome},
                    created_at=now - timedelta(days=i),
                )
            )
        session.add(
            Call(
                id=uuid.uuid4(),
                team_id=team_id,
                lead_id=crew["assigned_lead"],
                user_id=ids["sales"],
                provider="ringostat",
                direction="outbound",
                state="analyzed",
                talk_sec=300,
                analysis={"quality_score": 8, "objections": ["Нет времени"]},
                created_at=now - timedelta(hours=2),
            )
        )
        await session.commit()

    r = clients["owner"].get(f"/api/v1/teams/{team_id}/sales-analytics?period=month")
    assert r.status_code == 200, r.text
    body = r.json()
    k = body["kpi"]
    assert k["dials"] == 4 and k["talks"] == 3 and k["goals"] == 1
    assert k["reach_rate"] == 0.75
    assert k["quality_avg"] == 8.0 and k["talk_avg_sec"] == 300
    assert k["overdue_callbacks"] == 1
    assert k["dials_plan"] and k["dials_plan"] > 100
    outcomes = {b["key"]: b["count"] for b in body["outcomes"]}
    assert outcomes["goal"] == 1 and outcomes["no_answer"] == 1
    assert body["objections"][0]["key"] == "нет времени"
    hot = next(t for t in body["by_temp"] if t["temp"] == "hot")
    assert hot["talks"] == 3 and hot["goals"] == 1
    steps = {s["key"]: s["count"] for s in body["funnel"]}
    assert steps["dials"] == 4 and steps["goals"] == 1
    sales_row = next(m for m in body["members"] if m["user_id"] == ids["sales"])
    assert sales_row["dials"] == 4 and sales_row["overdue"] == 1 and sales_row["hot_leads"] == 1
    # Правило: < 50% плана по наборам → предупреждение по имени.
    assert any(i["kind"] == "warn" and "плана" in i["text"] for i in body["insights"])

    # Селз не видит аналитику.
    assert clients["sales"].get(f"/api/v1/teams/{team_id}/sales-analytics").status_code == 403
