"""Обработка записи звонка: скачать → расшифровать → разобрать.

Запускается после webhook провайдера (через очередь или в процессе).
Каждый шаг пишет результат сразу: упадёт разбор — расшифровка уже
сохранена и видна в карточке. Ошибки не роняют ничего снаружи, а
ложатся в ``Call.error``.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from leadgen.config import get_settings
from leadgen.db.models import Call, Funnel, Lead, LeadActivity
from leadgen.db.session import session_factory

logger = logging.getLogger(__name__)

MAX_RECORDING_BYTES = 60 * 1024 * 1024
STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"
CALL_OUTCOMES = (
    "goal",
    "callback",
    "thinking",
    "no_answer",
    "refused",
    "wrong_number",
)


async def _download(url: str) -> bytes:
    from leadgen.core.services.telephony import guarded_stream

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=False) as client:
        resp = await guarded_stream(client, url)
        try:
            resp.raise_for_status()
            chunks: list[bytes] = []
            size = 0
            async for chunk in resp.aiter_bytes():
                size += len(chunk)
                if size > MAX_RECORDING_BYTES:
                    raise ValueError("recording is too large")
                chunks.append(chunk)
        finally:
            await resp.aclose()
    return b"".join(chunks)


def _segments(stt: dict[str, Any]) -> list[dict[str, Any]]:
    """Слова ElevenLabs → реплики. Две дорожки (multichannel) дают
    точное «кто говорит»: канал 0 — сотрудник, 1 — клиент; иначе
    используем диаризацию (s0/s1)."""
    words: list[dict[str, Any]] = []
    if "transcripts" in stt:
        for tr in stt["transcripts"]:
            for w in tr.get("words") or []:
                words.append({**w, "_ch": tr.get("channel_index", 0)})
        words.sort(key=lambda w: w.get("start") or 0)
    else:
        words = list(stt.get("words") or [])

    out: list[dict[str, Any]] = []
    for w in words:
        if w.get("type") == "audio_event":
            continue
        if "_ch" in w:
            speaker = "rep" if w["_ch"] == 0 else "client"
        else:
            speaker = f"s{w.get('speaker_id', '0')}".replace("speaker_", "")
        text = w.get("text") or ""
        if out and out[-1]["speaker"] == speaker:
            out[-1]["text"] += text
        else:
            if w.get("type") == "spacing":
                continue
            out.append(
                {
                    "speaker": speaker,
                    "start": round(float(w.get("start") or 0), 1),
                    "text": text,
                }
            )
    for seg in out:
        seg["text"] = seg["text"].strip()
    return [seg for seg in out if seg["text"]]


async def transcribe(audio: bytes, *, stereo_hint: bool = True) -> list[dict[str, Any]]:
    settings = get_settings()
    if not settings.elevenlabs_api_key:
        raise RuntimeError("ELEVENLABS_API_KEY is not set")
    data: dict[str, Any] = {
        "model_id": settings.elevenlabs_stt_model,
        "timestamps_granularity": "word",
    }
    if stereo_hint:
        data["use_multi_channel"] = "true"
    else:
        data["diarize"] = "true"
        data["num_speakers"] = "2"
    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(
            STT_URL,
            headers={"xi-api-key": settings.elevenlabs_api_key},
            data=data,
            files={"file": ("call.wav", audio, "audio/wav")},
        )
    if resp.status_code >= 400 and stereo_hint:
        # Запись оказалась моно — многодорожечный режим не подходит,
        # повторяем с диаризацией.
        return await transcribe(audio, stereo_hint=False)
    resp.raise_for_status()
    return _segments(resp.json())


def _render(segments: list[dict[str, Any]]) -> str:
    labels = {"rep": "Менеджер", "client": "Клиент"}
    return "\n".join(
        f"{labels.get(s['speaker'], s['speaker'])}: {s['text']}"
        for s in segments
    )


async def analyze(
    segments: list[dict[str, Any]], funnel: Funnel | None
) -> dict[str, Any]:
    """Разбор звонка Claude: итог, следующий шаг, исход, возражения,
    качество. Контекст — цель, скрипт и возражения воронки."""
    import anthropic

    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    funnel_ctx = ""
    if funnel is not None:
        objections = "; ".join(
            f"{o.get('objection')} → {o.get('answer')}"
            for o in (funnel.objections or [])
            if o.get("objection")
        )
        funnel_ctx = (
            f"Цель воронки: {funnel.goal_name or '—'}\n"
            f"Скрипт: {funnel.script or '—'}\n"
            f"Известные возражения и ответы: {objections or '—'}\n"
        )
    system = (
        "Ты разбираешь запись холодного B2B-звонка для отдела продаж. "
        "Отвечай ТОЛЬКО одним JSON без markdown, на языке разговора "
        "(украинский или русский). Если метки говорящих s0/s1 — сам "
        "определи, кто менеджер, а кто клиент. Не выдумывай того, чего "
        "нет в тексте."
    )
    user = (
        f"{funnel_ctx}\nРасшифровка:\n{_render(segments)}\n\n"
        'Верни JSON: {"summary": "2-3 предложения", '
        '"next_step": "конкретный следующий шаг или null", '
        f'"suggested_outcome": одно из {list(CALL_OUTCOMES)}, '
        '"callback_hint": "когда перезвонить, если клиент назвал время, иначе null", '
        '"objections": ["возражения клиента"], '
        '"sentiment": "positive|neutral|negative", '
        '"quality_score": 0-10, '
        '"quality_notes": "что менеджер сделал хорошо и что улучшить, 1-2 предложения"}'
    )
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    message = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=800,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    try:
        from leadgen.core.services import usage_tracker

        await usage_tracker.record_claude_usage(message.usage)
    except Exception:  # noqa: BLE001 — учёт затрат не роняет разбор
        pass
    raw = "".join(
        getattr(block, "text", "") for block in message.content
    ).strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
    result = json.loads(raw)
    if result.get("suggested_outcome") not in CALL_OUTCOMES:
        result["suggested_outcome"] = None
    return result


async def process_call(call_id: uuid.UUID) -> None:
    """Полный цикл для одного звонка. Идемпотентен по состоянию."""
    async with session_factory() as session:
        call = await session.get(Call, call_id)
        if call is None or not call.recording_url or not call.record_consent:
            return
        if call.state in ("analyzed",):
            return
        try:
            if not call.transcript:
                audio = await _download(call.recording_url)
                call.transcript = await transcribe(audio)
                call.state = "transcribed"
                await session.commit()

            funnel = None
            if call.lead_id is not None:
                lead = await session.get(Lead, call.lead_id)
                if lead is not None and lead.funnel_id is not None:
                    funnel = (
                        await session.execute(
                            select(Funnel)
                            .where(Funnel.id == lead.funnel_id)
                            .options(selectinload(Funnel.steps))
                        )
                    ).scalar_one_or_none()

            if call.transcript:
                call.analysis = await analyze(call.transcript, funnel)
                call.state = "analyzed"
                if call.lead_id is not None and call.user_id is not None:
                    session.add(
                        LeadActivity(
                            lead_id=call.lead_id,
                            user_id=call.user_id,
                            team_id=call.team_id,
                            kind="call_analyzed",
                            payload={
                                "call_id": str(call.id),
                                "summary": call.analysis.get("summary"),
                                "next_step": call.analysis.get("next_step"),
                                "talk_sec": call.talk_sec,
                            },
                        )
                    )
            call.error = None
        except Exception as exc:  # noqa: BLE001
            logger.warning("process_call %s failed: %s", call_id, exc)
            call.error = str(exc)[:500]
            if call.state == "completed":
                call.state = "failed"
        call.completed_at = call.completed_at or datetime.now(timezone.utc)
        await session.commit()


async def schedule(call_id: uuid.UUID) -> None:
    """В очередь, если есть Redis; иначе фоном в этом процессе."""
    settings = get_settings()
    if settings.redis_url:
        try:
            from arq.connections import RedisSettings, create_pool

            pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
            try:
                await pool.enqueue_job("process_call_job", str(call_id))
            finally:
                await pool.close()
            return
        except Exception:  # noqa: BLE001
            logger.exception("process_call enqueue failed; running inline")
    from leadgen.utils import spawn

    spawn(process_call(call_id), name=f"process_call:{call_id}")
