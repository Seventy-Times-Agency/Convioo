"""Лента уведомлений в приложении: запись, вкладка «Важное», счётчики,
«прочитать все», чужие уведомления не видны."""

from __future__ import annotations

import pytest

from leadgen.core.services.account.notification_feed import notify

pytest_plugins = ["tests.test_team_roles_wave1"]


@pytest.mark.asyncio
async def test_feed_tabs_counts_and_read(crew, patched_session_factory):
    sales_id = crew["ids"]["sales"]
    await notify(sales_id, kind="hot_reply", title="Горячий ответ: Аврора", urgent=True, link="/app/work/letters")
    await notify(sales_id, kind="search_done", title="Поиск готов")
    await notify(crew["ids"]["manager"], kind="goal", title="Чужое")

    c = crew["clients"]["sales"]
    r = c.get("/api/v1/notifications")
    assert r.status_code == 200, r.text
    body = r.json()
    assert [n["title"] for n in body["items"]] == ["Поиск готов", "Горячий ответ: Аврора"]
    assert body["unread"] == 2 and body["unread_important"] == 1

    important = c.get("/api/v1/notifications", params={"important": True}).json()
    assert [n["kind"] for n in important["items"]] == ["hot_reply"]

    hot_id = important["items"][0]["id"]
    r = c.post("/api/v1/notifications/read", json={"ids": [hot_id]})
    assert r.json() == {"unread": 1, "unread_important": 0}
    r = c.post("/api/v1/notifications/read", json={"all": True})
    assert r.json() == {"unread": 0, "unread_important": 0}
    assert c.get("/api/v1/notifications/unread").json()["unread"] == 0
