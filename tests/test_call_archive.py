"""Архив звонков по сотруднику и сессии общего ИИ-разбора."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from leadgen.adapters.web_api.routes.sales import call_archive as archive_mod
from leadgen.core.services.sales import call_review as cr
from leadgen.db.models import Call

pytest_plugins = ["tests.test_team_roles_wave1"]


async def _call(maker, crew, who: str, *, days_ago: int = 0, transcript: bool = True) -> uuid.UUID:
    async with maker() as session:
        c = Call(
            id=uuid.uuid4(),
            team_id=crew["team_id"],
            lead_id=crew["assigned_lead"],
            user_id=crew["ids"][who],
            provider="ringostat",
            direction="out",
            state="analyzed",
            talk_sec=95,
            transcript=(
                [
                    {"speaker": "rep", "text": "Добрый день, мы делаем сайты для стоматологий."},
                    {"speaker": "client", "text": "Дорого, у нас уже есть подрядчик."},
                ]
                if transcript
                else None
            ),
            analysis={"summary": "Клиент отказался", "quality_score": 5, "objections": ["дорого"]},
            created_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
        )
        session.add(c)
        await session.commit()
        return c.id


@pytest.mark.asyncio
async def test_who_sees_whose_calls(crew, patched_session_factory):
    team = crew["team_id"]
    await _call(patched_session_factory, crew, "sales")
    await _call(patched_session_factory, crew, "admin")

    assert crew["clients"]["sales"].get(f"/api/v1/teams/{team}/call-archive/people").status_code == 403

    people = crew["clients"]["manager"].get(f"/api/v1/teams/{team}/call-archive/people").json()
    roles = {p["role"] for p in people}
    assert roles == {"manager", "sales"}  # себя и продажников, не РОПа и владельца
    assert any(p["user_id"] == crew["ids"]["sales"] and p["calls"] == 1 for p in people)

    r = crew["clients"]["manager"].get(
        f"/api/v1/teams/{team}/call-archive", params={"user_id": crew["ids"]["admin"]}
    )
    assert r.status_code == 403
    owner_people = crew["clients"]["owner"].get(f"/api/v1/teams/{team}/call-archive/people").json()
    assert {p["role"] for p in owner_people} >= {"owner", "admin", "manager", "sales"}


@pytest.mark.asyncio
async def test_archive_filters_by_period(crew, patched_session_factory):
    team = crew["team_id"]
    await _call(patched_session_factory, crew, "sales", days_ago=0)
    await _call(patched_session_factory, crew, "sales", days_ago=10)
    today = datetime.now(timezone.utc).date()
    r = crew["clients"]["manager"].get(
        f"/api/v1/teams/{team}/call-archive",
        params={"user_id": crew["ids"]["sales"], "date_from": str(today - timedelta(days=3)), "date_to": str(today)},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["stats"]["total"] == 1
    assert body["calls"][0]["summary"] == "Клиент отказался"
    all_calls = crew["clients"]["manager"].get(
        f"/api/v1/teams/{team}/call-archive", params={"user_id": crew["ids"]["sales"]}
    ).json()
    assert all_calls["stats"]["total"] == 2


class _Msg:
    def __init__(self, text: str) -> None:
        self.content = [type("B", (), {"text": text})()]
        self.usage = None


@pytest.mark.asyncio
async def test_review_session_is_saved_with_result(crew, patched_session_factory, monkeypatch):
    from leadgen.config import get_settings

    team = crew["team_id"]
    ids = [await _call(patched_session_factory, crew, "sales") for _ in range(3)]
    no_text = await _call(patched_session_factory, crew, "sales", transcript=False)

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    get_settings.cache_clear()
    sent: dict = {}

    async def fake_create(client, **kw):
        sent.update(kw)
        return _Msg(json.dumps({
            "summary": "Менеджер сдаётся на возражении о цене.",
            "score": 5,
            "verdict": "weak",
            "mistakes": [{"title": "Нет выявления потребности", "calls": [1, 2], "example": "", "fix": "Спросить о задачах"}],
            "objections": [{"text": "дорого", "calls": [1, 2, 3], "handled": "badly", "better_answer": "Сравнить с ценой клиента"}],
            "strengths": ["Вежливость"],
            "recommendations": ["Отработать возражение «дорого»"],
            "per_call": [{"n": 1, "score": 5, "note": "сдался"}],
        }))

    monkeypatch.setattr(cr.usage_tracker, "tracked_create", fake_create)
    spawned: list = []
    monkeypatch.setattr(archive_mod, "spawn", lambda coro, name=None: spawned.append(coro))

    client = crew["clients"]["manager"]
    r = client.post(
        f"/api/v1/teams/{team}/call-reviews",
        json={"call_ids": [str(x) for x in ids + [no_text]], "focus": "работа с ценой"},
    )
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    assert r.json()["status"] == "running" and r.json()["calls"] == 4
    await spawned[0]
    get_settings.cache_clear()

    review = client.get(f"/api/v1/call-reviews/{rid}").json()
    assert review["status"] == "done"
    assert review["result"]["objections"][0]["text"] == "дорого"
    assert set(review["result"]["call_map"]) == {"1", "2", "3"}  # без звонка без расшифровки
    assert "работа с ценой" in sent["messages"][0]["content"]

    history = client.get(f"/api/v1/teams/{team}/call-reviews").json()
    assert history[0]["id"] == rid and "result" not in history[0]
    # Продажнику разборы недоступны.
    assert crew["clients"]["sales"].get(f"/api/v1/call-reviews/{rid}").status_code == 403
    # Звонки РОПа тимлид разбирать не может.
    admin_call = await _call(patched_session_factory, crew, "admin")
    r = client.post(f"/api/v1/teams/{team}/call-reviews", json={"call_ids": [str(admin_call)]})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_recording_supports_range_and_archive_access(crew, patched_session_factory, monkeypatch):
    import leadgen.core.services.sales.telephony as tel

    cid = await _call(patched_session_factory, crew, "sales")
    async with patched_session_factory() as session:
        (await session.get(Call, cid)).recording_url = "https://example.com/r.wav"
        (await session.get(Call, cid)).lead_id = None  # лид удалён — доступ только по архиву
        await session.commit()

    seen: dict = {}

    class _Up:
        status_code = 206
        headers = {"content-type": "audio/wav", "content-length": "4", "content-range": "bytes 0-3/100"}

        async def aiter_raw(self):
            yield b"RIFF"

        async def aclose(self):
            pass

    async def fake_stream(client, url, headers=None):
        seen["headers"] = headers
        return _Up()

    monkeypatch.setattr(tel, "guarded_stream", fake_stream)
    r = crew["clients"]["manager"].get(f"/api/v1/calls/{cid}/recording", headers={"Range": "bytes=0-3"})
    assert r.status_code == 206
    assert r.headers["content-range"] == "bytes 0-3/100" and r.headers["accept-ranges"] == "bytes"
    assert r.content == b"RIFF"
    assert seen["headers"] == {"Range": "bytes=0-3"}
    # Другой продажник чужую запись не получит.
    assert crew["clients"]["sales2"].get(f"/api/v1/calls/{cid}/recording").status_code == 404


@pytest.mark.asyncio
async def test_truncated_answer_is_saved_and_failed_review_can_be_retried(crew, patched_session_factory, monkeypatch):
    from leadgen.config import get_settings

    team = crew["team_id"]
    ids = [await _call(patched_session_factory, crew, "sales") for _ in range(2)]
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    get_settings.cache_clear()
    answers = [
        _Msg("not json at all"),
        # Оборвался на середине — сохраняем то, что успело прийти.
        _Msg('{"summary": "Сдаётся на цене", "mistakes": [{"title": "Нет вопросов", "calls": [1]}], "per_call": [{"n": 1, "sc'),
    ]

    async def fake_create(client, **kw):
        return answers.pop(0)

    monkeypatch.setattr(cr.usage_tracker, "tracked_create", fake_create)
    spawned: list = []
    monkeypatch.setattr(archive_mod, "spawn", lambda coro, name=None: spawned.append(coro))
    client = crew["clients"]["manager"]
    rid = client.post(f"/api/v1/teams/{team}/call-reviews", json={"call_ids": [str(x) for x in ids]}).json()["id"]
    await spawned.pop()
    assert client.get(f"/api/v1/call-reviews/{rid}").json()["status"] == "failed"

    r = client.post(f"/api/v1/call-reviews/{rid}/retry")
    assert r.status_code == 200, r.text
    await spawned.pop()
    get_settings.cache_clear()
    review = client.get(f"/api/v1/call-reviews/{rid}").json()
    assert review["status"] == "done"
    assert review["result"]["summary"] == "Сдаётся на цене"
    assert review["result"]["truncated"] is True
