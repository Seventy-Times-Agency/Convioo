"""Звонки: диалог по фразам без эха, строгая шкала, автоматика по
настройкам команды и разбор по кнопке."""

from __future__ import annotations

import uuid

import pytest

from leadgen.core.services.sales.telephony import processing as proc
from leadgen.core.services.sales.telephony import rubric
from leadgen.db.models import Call, Team

pytest_plugins = ["tests.test_team_roles_wave1"]


def _w(text, start, end):
    return {"text": text, "start": start, "end": end, "type": "word"}


def test_segments_build_a_dialog_and_drop_echo():
    stt = {
        "transcripts": [
            {
                "channel_index": 0,
                "words": [
                    _w("Добрий", 0.0, 0.4), {"text": " ", "type": "spacing"}, _w("день,", 0.4, 0.8),
                    _w("мене", 0.9, 1.1), {"text": " ", "type": "spacing"}, _w("звати", 1.1, 1.5),
                    _w("Ок", 4.0, 4.2),
                ],
            },
            {
                "channel_index": 1,
                "words": [
                    # Эхо менеджера на дорожке клиента в то же время.
                    _w("Добрий", 0.05, 0.45), {"text": " ", "type": "spacing"}, _w("день", 0.45, 0.85),
                    _w("Слухаю", 2.0, 2.5), {"text": " ", "type": "spacing"}, _w("вас", 2.5, 2.8),
                ],
            },
        ]
    }
    out = proc._segments(stt, rep_channel=0)
    assert [s["speaker"] for s in out] == ["rep", "client", "rep"]
    assert out[0]["text"] == "Добрий день, мене звати"
    assert out[1]["text"] == "Слухаю вас"


def test_strict_score_and_caps():
    full = [{"key": k, "level": "met"} for k, *_ in rubric.CRITERIA]
    assert rubric.score(full) == 10
    # Всё «выполнено», кроме следующего шага — не выше 5.
    no_step = [dict(r, level="not_met") if r["key"] == "next_step" else r for r in full]
    assert rubric.score(no_step) == 5
    # Попытка выявить потребность провалена — не выше 6.
    no_disc = [dict(r, level="not_met") if r["key"] == "discovery" else r for r in full]
    assert rubric.score(no_disc) <= 6
    # «Неприменимо» не тянет балл вниз.
    na = [dict(r, level="na") if r["key"] == "objections" else r for r in full]
    assert rubric.score(na) == 10
    assert rubric.score([]) is None


async def _call(maker, crew, **kw) -> uuid.UUID:
    kw.setdefault("talk_sec", 120)
    async with maker() as session:
        c = Call(
            id=uuid.uuid4(),
            team_id=crew["team_id"],
            lead_id=crew["assigned_lead"],
            user_id=crew["ids"]["sales"],
            provider="ringostat",
            direction="out",
            state="completed",
            recording_url="https://example.com/r.wav",
            **kw,
        )
        session.add(c)
        await session.commit()
        return c.id


@pytest.fixture
def fake_ai(monkeypatch):
    calls = {"transcribe": 0, "analyze": 0}

    async def download(url):
        return b"RIFF"

    async def transcribe(audio, **kw):
        calls["transcribe"] += 1
        return [{"speaker": "rep", "text": "Добрий день"}, {"speaker": "client", "text": "Не цікаво"}]

    async def analyze(segments, funnel):
        calls["analyze"] += 1
        return {"summary": "ок", "quality_score": 3}

    monkeypatch.setattr(proc, "_download", download)
    monkeypatch.setattr(proc, "transcribe", transcribe)
    monkeypatch.setattr(proc, "analyze", analyze)
    return calls


@pytest.mark.asyncio
async def test_auto_mode_follows_team_settings(crew, patched_session_factory, fake_ai):
    cid = await _call(patched_session_factory, crew)
    # По умолчанию: расшифровка — да, оценка — нет.
    await proc.process_call(cid, "auto")
    async with patched_session_factory() as session:
        c = await session.get(Call, cid)
        assert c.transcript and c.analysis is None and c.state == "transcribed"
    assert fake_ai == {"transcribe": 1, "analyze": 0}

    # Кнопка «Разобрать» — оценка независимо от настроек.
    await proc.process_call(cid, "full")
    async with patched_session_factory() as session:
        assert (await session.get(Call, cid)).analysis["summary"] == "ок"

    # Всё выключено — после звонка ничего не тратится.
    async with patched_session_factory() as session:
        (await session.get(Team, crew["team_id"])).call_auto_transcribe = False
        await session.commit()
    cid2 = await _call(patched_session_factory, crew)
    await proc.process_call(cid2, "auto")
    assert fake_ai["transcribe"] == 1


@pytest.mark.asyncio
async def test_short_calls_are_not_scored(crew, patched_session_factory, fake_ai):
    cid = await _call(patched_session_factory, crew, talk_sec=12)
    await proc.process_call(cid, "full")
    async with patched_session_factory() as session:
        c = await session.get(Call, cid)
    assert c.analysis["too_short"] is True
    assert fake_ai["analyze"] == 0


@pytest.mark.asyncio
async def test_automation_settings_owner_and_head_only(crew, patched_session_factory, monkeypatch):
    import leadgen.core.services.sales.telephony.processing as p

    team = crew["team_id"]
    url = f"/api/v1/teams/{team}/telephony/automation"
    assert crew["clients"]["manager"].patch(url, json={"auto_analyze": True}).status_code == 403
    r = crew["clients"]["admin"].patch(url, json={"auto_analyze": True})
    assert r.json() == {"auto_transcribe": True, "auto_analyze": True}
    # Без расшифровки оценка выключается сама.
    r = crew["clients"]["owner"].patch(url, json={"auto_transcribe": False})
    assert r.json() == {"auto_transcribe": False, "auto_analyze": False}

    # «Разобрать» по кнопке доступен тимлиду через архив и идёт в режиме full.
    cid = await _call(patched_session_factory, crew)
    seen = {}

    async def fake_schedule(call_id, mode="auto"):
        seen["mode"] = mode

    monkeypatch.setattr(p, "schedule", fake_schedule)
    r = crew["clients"]["manager"].post(f"/api/v1/calls/{cid}/reanalyze")
    assert r.status_code == 200, r.text
    assert seen["mode"] == "full"


def _wav(channels: int) -> bytes:
    import struct

    fmt = struct.pack("<HHIIHH", 1, channels, 8000, 8000 * 2 * channels, 2 * channels, 16)
    return b"RIFF" + struct.pack("<I", 36) + b"WAVE" + b"fmt " + struct.pack("<I", 16) + fmt + b"data" + struct.pack("<I", 0)


def test_wav_channels_and_diarized_labels():
    assert proc.wav_channels(_wav(2)) == 2
    assert proc.wav_channels(_wav(1)) == 1
    assert proc.wav_channels(b"not a wav") is None
    segs = [
        {"speaker": "s0", "text": "Алло"},
        {"speaker": "s1", "text": "Добрий день, мене звати Данило, компанія Seventy Times"},
        {"speaker": "s0", "text": "Слухаю"},
    ]
    out = proc._label_diarized(segs)
    assert [s["speaker"] for s in out] == ["client", "rep", "client"]


@pytest.mark.asyncio
async def test_mono_recording_is_diarized_not_one_blob(monkeypatch):
    sent: list[dict] = []

    class _Resp:
        status_code = 200

        def __init__(self, body):
            self._body = body

        def raise_for_status(self):
            pass

        def json(self):
            return self._body

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, data=None, files=None):
            sent.append(dict(data))
            return _Resp({"words": [
                {"text": "Алло", "start": 0, "end": 0.5, "type": "word", "speaker_id": "speaker_0"},
                {"text": "Мене звати Данило", "start": 1.5, "end": 3, "type": "word", "speaker_id": "speaker_1"},
            ]})

    from leadgen.config import get_settings

    monkeypatch.setenv("ELEVENLABS_API_KEY", "x")
    get_settings.cache_clear()
    monkeypatch.setattr(proc.httpx, "AsyncClient", _Client)
    try:
        out = await proc.transcribe(_wav(1), rep_channel=0)
    finally:
        get_settings.cache_clear()
    assert len(sent) == 1 and sent[0].get("diarize") == "true" and "use_multi_channel" not in sent[0]
    assert [s["speaker"] for s in out] == ["client", "rep"]


@pytest.mark.asyncio
async def test_label_turns_splits_one_blob_into_dialog(monkeypatch):
    from leadgen.config import get_settings

    words = []
    t = 0.0
    for phrase in ["Ваша розмова може бути записана.", "Добрий день, мене звати Данило.", "Слухаю вас.", "Звідки у вас клієнти?", "З Instagram."]:
        for w in phrase.split():
            words.append({"text": w, "start": t, "end": t + 0.3, "type": "word"})
            words.append({"text": " ", "type": "spacing"})
            t += 0.32
        t += 0.6  # пауза между репликами
    seen = {}

    class _M:
        def __init__(self, text):
            self.content = [type("B", (), {"text": text})()]

    async def fake_create(client, **kw):
        seen["prompt"] = kw["messages"][0]["content"]
        return _M('{"labels": ["s", "r", "c", "r", "c"]}')

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    get_settings.cache_clear()
    monkeypatch.setattr(proc.usage_tracker, "tracked_create", fake_create)
    try:
        out = await proc.label_turns(words)
    finally:
        get_settings.cache_clear()
    assert [s["speaker"] for s in out] == ["system", "rep", "client", "rep", "client"]
    assert out[1]["text"] == "Добрий день, мене звати Данило."
    assert "4. З Instagram." in seen["prompt"]
    assert proc._looks_messy([{"speaker": "s0", "text": "x" * 400}]) is True
