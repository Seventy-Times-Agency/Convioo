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
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from leadgen.config import get_settings
from leadgen.core.services.search import usage_tracker
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
    from leadgen.core.services.sales.telephony import guarded_stream

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


#: Пауза внутри дорожки, после которой начинается новая фраза.
PHRASE_GAP_SEC = 0.9
#: Насколько похожа фраза на одновременную фразу другой дорожки, чтобы
#: считать её эхом (голос одного слышен в микрофоне другого).
ECHO_SIMILARITY = 0.75


def _phrases(words: list[dict[str, Any]], speaker: str) -> list[dict[str, Any]]:
    """Слова одной дорожки → фразы (по паузам)."""
    out: list[dict[str, Any]] = []
    for w in words:
        if w.get("type") == "audio_event":
            continue
        start = float(w.get("start") or 0)
        end = float(w.get("end") or start)
        text = w.get("text") or ""
        if w.get("type") == "spacing":
            if out:
                out[-1]["text"] += text
            continue
        if out and start - out[-1]["end"] <= PHRASE_GAP_SEC:
            prev = out[-1]["text"]
            # Без отдельного «пробела» между словами — ставим сами.
            if prev and not prev[-1].isspace() and text[:1].isalnum():
                prev += " "
            out[-1]["text"] = prev + text
            out[-1]["end"] = end
        else:
            out.append({"speaker": speaker, "start": start, "end": end, "text": text})
    for ph in out:
        ph["text"] = " ".join(ph["text"].split())
    return [ph for ph in out if ph["text"]]


def _is_echo(ph: dict[str, Any], others: list[dict[str, Any]]) -> bool:
    import difflib

    for o in others:
        if o["end"] < ph["start"] - 1 or o["start"] > ph["end"] + 1:
            continue
        a, b = ph["text"].lower(), o["text"].lower()
        # Короткие «да», «угу» поверх чужой речи — настоящие реплики.
        if len(a) > len(b) or len(a) < 8:
            continue
        # Какая доля этой фразы целиком есть в одновременной фразе другой
        # дорожки: эхо обычно — обрывок чужой реплики.
        same = sum(m.size for m in difflib.SequenceMatcher(None, a, b).get_matching_blocks())
        if same / len(a) >= ECHO_SIMILARITY:
            return True
    return False


def _segments(
    stt: dict[str, Any], rep_channel: int | None = 0
) -> list[dict[str, Any]]:
    """Слова ElevenLabs → реплики диалога.

    Две дорожки (multichannel) дают точное «кто говорит»:
    ``rep_channel`` — дорожка сотрудника. Сначала каждая дорожка
    собирается во фразы по паузам, потом фразы выстраиваются по времени.
    Раньше слова двух дорожек сортировались вперемешку, и где люди
    перебивали друг друга или голос одного попадал в микрофон другого,
    реплики рвались на обрывки. Эхо (та же фраза на чужой дорожке в то
    же время) отбрасывается. Без дорожек — диаризация (s0/s1).
    """
    rep = 0 if rep_channel is None else rep_channel
    phrases: list[dict[str, Any]] = []
    if "transcripts" in stt:
        per_channel: dict[int, list[dict[str, Any]]] = {}
        for tr in stt["transcripts"]:
            ch = int(tr.get("channel_index", 0) or 0)
            speaker = "rep" if ch == rep else "client"
            per_channel[ch] = _phrases(tr.get("words") or [], speaker)
        for ch, items in per_channel.items():
            others = [p for c, lst in per_channel.items() if c != ch for p in lst]
            phrases += [p for p in items if not _is_echo(p, others)]
    else:
        by_speaker: dict[str, list[dict[str, Any]]] = {}
        for w in stt.get("words") or []:
            sp = f"s{w.get('speaker_id', '0')}".replace("speaker_", "")
            by_speaker.setdefault(sp, []).append(w)
        for sp, words in by_speaker.items():
            phrases += _phrases(words, sp)
    phrases.sort(key=lambda p: p["start"])

    out: list[dict[str, Any]] = []
    for ph in phrases:
        if out and out[-1]["speaker"] == ph["speaker"]:
            out[-1]["text"] += " " + ph["text"]
        else:
            out.append({"speaker": ph["speaker"], "start": round(ph["start"], 1), "text": ph["text"]})
    return out


def wav_channels(audio: bytes) -> int | None:
    """Число дорожек WAV по заголовку (None — не WAV или не разобрать)."""
    import struct

    if len(audio) < 44 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        return None
    i = 12
    while i + 8 <= len(audio) and i < 4096:
        chunk, size = audio[i : i + 4], struct.unpack("<I", audio[i + 4 : i + 8])[0]
        if chunk == b"fmt " and i + 12 <= len(audio):
            return struct.unpack("<H", audio[i + 10 : i + 12])[0]
        i += 8 + size + (size & 1)
    return None


_INTRO = ("меня зовут", "мене звати", "my name is", "компания", "компанія", "company", "звоню", "дзвоню", "calling from")


def _label_diarized(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Диаризация даёт s0/s1 без смысла. Менеджер — тот, кто
    представляется; если не понять — тот, кто говорит больше (в холодном
    звонке это почти всегда звонящий)."""
    speakers = {s["speaker"] for s in segments}
    if not speakers or speakers <= {"rep", "client"}:
        return segments
    intro: dict[str, int] = {}
    volume: dict[str, int] = {}
    for s in segments:
        text = s["text"].lower()
        intro[s["speaker"]] = intro.get(s["speaker"], 0) + sum(k in text for k in _INTRO)
        volume[s["speaker"]] = volume.get(s["speaker"], 0) + len(text)
    rep = max(speakers, key=lambda sp: (intro.get(sp, 0), volume.get(sp, 0)))
    return [{**s, "speaker": "rep" if s["speaker"] == rep else "client"} for s in segments]


async def transcribe(
    audio: bytes, *, stereo_hint: bool | None = None, rep_channel: int | None = 0
) -> list[dict[str, Any]]:
    """Запись → реплики. Стерео — делим по дорожкам; моно — просим сервис
    различить двух собеседников. Сколько дорожек, смотрим по самому
    файлу: у провайдера бывают и те и другие, а моно в многодорожечном
    режиме возвращается одной сплошной репликой."""
    settings = get_settings()
    if not settings.elevenlabs_api_key:
        raise RuntimeError("ELEVENLABS_API_KEY is not set")
    if stereo_hint is None:
        channels = wav_channels(audio)
        stereo_hint = channels is None or channels >= 2
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
        return await transcribe(audio, stereo_hint=False, rep_channel=rep_channel)
    resp.raise_for_status()
    data = resp.json()
    if stereo_hint and len(data.get("transcripts") or []) < 2:
        # Сервис увидел одну дорожку — без диаризации это одна реплика.
        return await transcribe(audio, stereo_hint=False, rep_channel=rep_channel)
    transcripts = data.get("transcripts") or []
    if len(transcripts) >= 2:
        segments = _segments(data, rep_channel)
        if not _looks_messy(segments):
            return segments
        # Дорожки есть, но голоса на них смешаны — размечаем по смыслу
        # слова самой полной дорожки.
        words = max(transcripts, key=lambda tr: len(tr.get("words") or [])).get("words") or []
    else:
        segments = _label_diarized(_segments(data, rep_channel))
        words = data.get("words") or []
    labelled = await label_turns(words)
    return labelled or segments


#: Пауза, после которой кусок для разметки ролей заканчивается; после
#: конца предложения хватает и короткой.
CHUNK_GAP_SEC = 0.35
CHUNK_SENTENCE_GAP_SEC = 0.1
MAX_LABEL_CHUNKS = 400


def _chunks(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Слова одной записи → короткие куски по паузам и концам фраз.
    Кусок мельче реплики: роль на нём почти всегда одна."""
    out: list[dict[str, Any]] = []
    for w in words:
        if w.get("type") == "audio_event":
            continue
        text = w.get("text") or ""
        if w.get("type") == "spacing":
            if out:
                out[-1]["text"] += text
            continue
        start = float(w.get("start") or 0)
        end = float(w.get("end") or start)
        if out:
            prev = out[-1]
            gap = start - prev["end"]
            sentence_end = prev["text"].rstrip()[-1:] in ".?!…"
            if gap <= CHUNK_GAP_SEC and not (sentence_end and gap > CHUNK_SENTENCE_GAP_SEC):
                if prev["text"] and not prev["text"][-1].isspace() and text[:1].isalnum():
                    prev["text"] += " "
                prev["text"] += text
                prev["end"] = end
                continue
        out.append({"start": start, "end": end, "text": text})
    for c in out:
        c["text"] = " ".join(c["text"].split())
    return [c for c in out if c["text"]]


def _looks_messy(segments: list[dict[str, Any]]) -> bool:
    """Одна сторона «говорит» почти всё в длинном разговоре — значит,
    голоса не разделились."""
    volume: dict[str, int] = {}
    for seg in segments:
        volume[seg["speaker"]] = volume.get(seg["speaker"], 0) + len(seg["text"])
    total = sum(volume.values())
    return total > 300 and max(volume.values(), default=0) / max(1, total) > 0.85


async def label_turns(words: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """Разметить роли по смыслу: Claude получает пронумерованные куски и
    возвращает только метку на каждый — текст и время остаются точными.
    None — разметить не вышло (оставляем диаризацию)."""
    import anthropic

    chunks = _chunks(words)
    settings = get_settings()
    if not chunks or len(chunks) > MAX_LABEL_CHUNKS or not settings.anthropic_api_key:
        return None
    numbered = "\n".join(f"{i}. {c['text']}" for i, c in enumerate(chunks))
    prompt = (
        "Это расшифровка холодного телефонного звонка, нарезанная на куски по "
        "паузам. Менеджер звонит компании и предлагает услугу; клиент — тот, "
        "кому звонят. В начале может быть автоответчик или робот компании "
        "(«ваша розмова може бути записана», «оцініть роботу», меню). Для "
        'каждого куска укажи, кто говорит: "r" — менеджер, "c" — клиент, '
        '"s" — автоответчик/робот. Если кусок явно содержит две стороны, '
        "отметь того, кто говорит большую часть. Верни ТОЛЬКО JSON "
        '{"labels": ["r", "c", ...]} — ровно по одной метке на каждый кусок, '
        f"всего {len(chunks)}.\n\nКуски:\n{numbered}"
    )
    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        msg = await usage_tracker.tracked_create(
            client,
            model=settings.anthropic_model,
            max_tokens=min(4000, 20 + 6 * len(chunks)),
            messages=[{"role": "user", "content": prompt}],
        )
        raw = "".join(getattr(b, "text", "") for b in msg.content)
        labels = json.loads(raw[raw.find("{") : raw.rfind("}") + 1]).get("labels") or []
    except Exception:  # noqa: BLE001 — разметка необязательна
        logger.warning("label_turns failed", exc_info=True)
        return None
    if len(labels) != len(chunks):
        return None
    names = {"r": "rep", "c": "client", "s": "system"}
    out: list[dict[str, Any]] = []
    for chunk, label in zip(chunks, labels, strict=False):
        speaker = names.get(str(label).strip().lower()[:1], "client")
        if out and out[-1]["speaker"] == speaker:
            out[-1]["text"] += " " + chunk["text"]
        else:
            out.append({"speaker": speaker, "start": round(chunk["start"], 1), "text": chunk["text"]})
    return out


def _render(segments: list[dict[str, Any]]) -> str:
    labels = {"rep": "Менеджер", "client": "Клиент", "system": "Автоответчик"}
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
    from leadgen.core.services.sales.telephony import rubric as _rubric

    share = _rubric.talk_share(segments)
    system = (
        "Ты строгий руководитель отдела продаж и оцениваешь запись холодного "
        "B2B-звонка. Твоя задача — честно показать, где менеджер работал плохо, "
        "а не подбодрить его. Отвечай ТОЛЬКО одним JSON без markdown, на языке "
        "разговора (украинский, русский или английский). Менеджер — тот, кто "
        "звонит и предлагает услугу; клиент — тот, кому позвонили. Метки "
        "«Менеджер»/«Клиент» расставлены по дорожкам записи и могут быть "
        "перепутаны местами, а s0/s1 не значат ничего: определи роли по смыслу "
        "реплик. Не выдумывай того, чего нет в тексте.\n\n" + _rubric.rubric_prompt()
    )
    share_line = (
        f"Доля речи клиента по объёму текста: {round(share * 100)}%.\n" if share is not None else ""
    )
    user = (
        f"{funnel_ctx}{share_line}\nРасшифровка:\n{_render(segments)}\n\n"
        'Верни JSON: {"summary": "2-3 предложения, что произошло", '
        '"next_step": "конкретный следующий шаг или null", '
        f'"suggested_outcome": одно из {list(CALL_OUTCOMES)}, '
        '"callback_hint": "когда перезвонить, если клиент назвал время, иначе null", '
        '"objections": ["возражения клиента"], '
        '"sentiment": "positive|neutral|negative", '
        + _rubric.rubric_json_hint() + ", "
        '"quality_notes": "главное, что менеджер сделал не так, и что делать иначе — 1-2 предложения, без утешений", '
        '"speakers_swapped": true если метки «Менеджер» и «Клиент» в расшифровке '
        'перепутаны местами, иначе false}'
    )
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    message = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=1600,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    # record_claude_usage сам глотает ошибки — учёт не роняет разбор.
    await usage_tracker.record_claude_usage(message.usage)
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
    # Балл считаем сами по шкале — модель склонна завышать «на глаз».
    result["quality_score"] = _rubric.score(result.get("rubric"))
    result["rubric_version"] = 1
    return result


async def _consent_withdrawn(session, call: Call) -> bool:
    """Согласие могли отозвать, пока шла расшифровка или разбор.

    Читаем из базы, а не из объекта в сессии: «Отменить запись» стирает
    данные в другом запросе, и наш устаревший объект иначе записал бы
    расшифровку обратно.
    """
    current = (
        await session.execute(
            select(Call.record_consent).where(Call.id == call.id)
        )
    ).scalar_one_or_none()
    if current:
        return False
    call.record_consent = False
    call.recording_url = None
    call.transcript = None
    call.analysis = None
    return True


#: Режимы обработки: ``auto`` — после звонка, по настройкам команды;
#: ``full`` — по кнопке: расшифровать (если нет) и оценить;
#: ``transcribe`` — только расшифровать (для общего разбора).
MODES = ("auto", "full", "transcribe")


async def process_call(call_id: uuid.UUID, mode: str = "auto") -> None:
    """Цикл для одного звонка. Идемпотентен по состоянию."""
    from leadgen.core.services.sales.telephony import rubric as _rubric
    from leadgen.db.models import Team

    async with session_factory() as session:
        call = await session.get(Call, call_id)
        if call is None or not call.recording_url or not call.record_consent:
            return
        # Расшифровка и разбор — расходы команды этого звонка.
        usage_tracker.bind_team(call.team_id)
        usage_tracker.set_stage("calls")
        if call.state in ("analyzed",) and mode != "full":
            return
        do_transcribe = do_analyze = mode == "full"
        if mode == "transcribe":
            do_transcribe = True
        elif mode == "auto":
            team = await session.get(Team, call.team_id) if call.team_id else None
            do_transcribe = team is None or bool(team.call_auto_transcribe)
            do_analyze = team is not None and bool(team.call_auto_analyze) and do_transcribe
        if not do_transcribe and not call.transcript:
            call.completed_at = call.completed_at or datetime.now(timezone.utc)
            await session.commit()
            return
        try:
            if not call.transcript:
                audio = await _download(call.recording_url)
                call.transcript = await transcribe(
                    audio, rep_channel=call.rep_channel
                )
                await usage_tracker.record(
                    "elevenlabs_stt_seconds", float(call.talk_sec or 0), stage="calls"
                )
                if await _consent_withdrawn(session, call):
                    await session.commit()
                    return
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

            if call.transcript and do_analyze and (call.talk_sec or 0) < _rubric.MIN_TALK_SEC and call.talk_sec is not None:
                # Недозвон, сброс, автоответчик — оценивать нечего, и
                # платить за это не нужно.
                call.analysis = {"summary": None, "too_short": True, "quality_score": None}
                call.state = "analyzed"
                do_analyze = False
            if call.transcript and do_analyze:
                call.analysis = await analyze(call.transcript, funnel)
                if await _consent_withdrawn(session, call):
                    await session.commit()
                    return
                # Дорожки записи у провайдера идут не в том порядке,
                # который мы считаем по умолчанию: при звонке из карточки
                # первым каналом оказывается клиент. Модель видит это по
                # смыслу — переставляем метки, чтобы и в карточке было
                # верно, кто что сказал.
                swapped = call.analysis.pop("speakers_swapped", False)
                # Если дорожка сотрудника известна по данным звонка,
                # метки уже верные — модели в этом не доверяем.
                if swapped and call.rep_channel is None:
                    flip = {"rep": "client", "client": "rep"}
                    call.transcript = [
                        {**seg, "speaker": flip.get(seg.get("speaker"), seg.get("speaker"))}
                        for seg in call.transcript
                    ]
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


async def schedule(call_id: uuid.UUID, mode: str = "auto") -> None:
    """В очередь, если есть Redis; иначе фоном в этом процессе."""
    settings = get_settings()
    if settings.redis_url:
        try:
            from arq.connections import RedisSettings, create_pool

            pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
            try:
                await pool.enqueue_job("process_call_job", str(call_id), mode)
            finally:
                await pool.close()
            return
        except Exception:  # noqa: BLE001
            logger.exception("process_call enqueue failed; running inline")
    from leadgen.utils import spawn

    spawn(process_call(call_id, mode), name=f"process_call:{call_id}")


#: Сколько ждём итог звонка от провайдера. Звонок из карточки длится
#: минуты; если за полчаса webhook не пришёл — он уже не придёт
#: (сотрудник не взял трубку, сбой у провайдера).
STALE_DIALING_AFTER = timedelta(minutes=30)


async def expire_stale_dialing(now: datetime | None = None) -> int:
    """Звонки, зависшие в «наборе», закрываем как несостоявшиеся.

    Иначе такой звонок висит вечно, а webhook следующего звонка на
    тот же номер может приклеиться к нему вместо нового.
    """
    now = now or datetime.now(timezone.utc)
    async with session_factory() as session:
        result = await session.execute(
            update(Call)
            .where(Call.state == "dialing")
            .where(Call.created_at < now - STALE_DIALING_AFTER)
            .values(
                state="missed",
                error="no result from the phone provider",
                completed_at=now,
            )
        )
        await session.commit()
    expired = result.rowcount or 0
    if expired:
        logger.info("telephony: expired %d stale dialing calls", expired)
    return expired
