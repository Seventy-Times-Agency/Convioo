"""Архив звонков по сотруднику и общий ИИ-разбор выбранных звонков.

Кто чьи звонки видит: тимлид (manager) — свои и продажников, РОП
(admin) — ещё и тимлидов, владелец и технический — всех. Продажник
архив не видит.

Разбор: до ``MAX_REVIEW_CALLS`` звонков с расшифровкой уходят в Claude
одним запросом; он ищет повторяющиеся ошибки менеджера, возражения
клиентов и как их лучше закрывать, сильные стороны и что делать дальше.
Каждый запрос — сессия ``CallReview``, они хранятся историей.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.config import get_settings
from leadgen.core.services.account.team_permissions import has_full_access, normalize_role
from leadgen.core.services.search import usage_tracker
from leadgen.db.models import Call, CallReview, Lead, TeamMembership, User
from leadgen.db.session import session_factory

logger = logging.getLogger(__name__)

MAX_REVIEW_CALLS = 30
#: Сколько символов расшифровки брать с одного звонка и со всех вместе
#: — чтобы запрос влез и стоил копейки.
PER_CALL_CHARS = 5_000
TOTAL_CHARS = 90_000

_RANK = {"sales": 1, "manager": 2, "admin": 3, "tech": 4, "owner": 5}


def rank(role: str | None) -> int:
    return _RANK.get(normalize_role(role), 0)


def can_open_archive(role: str | None) -> bool:
    return rank(role) >= _RANK["manager"]


def can_view(caller_role: str | None, caller_id: int, target_role: str | None, target_id: int) -> bool:
    if target_id == caller_id:
        return True
    if has_full_access(caller_role):
        return True
    return rank(target_role) < rank(caller_role)


async def viewable_people(
    session: AsyncSession, team_id: uuid.UUID, caller_id: int, caller_role: str
) -> list[dict[str, Any]]:
    """Люди команды, чьи звонки caller может смотреть."""
    rows = (
        await session.execute(
            select(TeamMembership, User)
            .join(User, User.id == TeamMembership.user_id)
            .where(TeamMembership.team_id == team_id)
        )
    ).all()
    out = []
    for m, u in rows:
        if not can_view(caller_role, caller_id, m.role, u.id):
            continue
        name = (
            u.display_name
            or " ".join(filter(None, [u.first_name, u.last_name]))
            or u.email
            or f"User {u.id}"
        )
        out.append({"user_id": u.id, "name": name, "role": normalize_role(m.role)})
    out.sort(key=lambda p: (-rank(p["role"]), p["name"].lower()))
    return out


def is_processing(call: Call, auto_transcribe: bool, auto_analyze: bool) -> bool:
    """Идёт ли сейчас обработка звонка сама — с учётом автоматики
    команды. Без этого «расшифрован» при выключенной оценке висел бы
    вечным «обрабатывается»."""
    if call.error or not call.recording_url or call.analysis:
        return False
    if call.state == "completed":
        return auto_transcribe
    if call.state == "transcribed":
        return auto_analyze
    return False


def _render(segments: list[dict[str, Any]] | None) -> str:
    labels = {"rep": "Менеджер", "client": "Клиент"}
    return "\n".join(
        f"{labels.get(s.get('speaker'), s.get('speaker'))}: {s.get('text', '')}"
        for s in (segments or [])
        if isinstance(s, dict)
    )


def _system() -> str:
    from leadgen.core.services.sales.telephony.rubric import rubric_prompt

    return (
        "Ты строгий руководитель отдела продаж и разбираешь пачку холодных "
        "B2B-звонков, чтобы увидеть ОБЩУЮ картину, а не пересказ каждого "
        "звонка. Задача — честно показать слабые места, а не подбодрить: "
        "хвали только то, что сделано грамотно и дало результат; неумелую "
        "или невнятную попытку называй ошибкой. Отвечай ТОЛЬКО одним JSON "
        "без markdown, на языке разговоров (украинский, русский или "
        "английский). Метки «Менеджер»/«Клиент» могут быть перепутаны — "
        "определяй роли по смыслу. Опирайся только на текст расшифровок, "
        "ничего не выдумывай; примеры — короткие цитаты из звонков.\n\n"
        + rubric_prompt()
        + "\nОценки per_call ставь по этой шкале: 10 — образцовый звонок, "
        "7 — хороший с мелкими недочётами, 5 — посредственный, ниже — плохой. "
        "Без конкретного следующего шага — не выше 5."
    )

_SCHEMA = (
    'Верни JSON: {"summary": "общая картина в 3-5 предложениях", '
    '"score": 0-10 средняя оценка работы, '
    '"verdict": "strong|ok|weak", '
    '"mistakes": [{"title": "повторяющаяся ошибка менеджера", "calls": [номера звонков], '
    '"example": "короткая цитата", "fix": "как делать правильно"}], '
    '"objections": [{"text": "возражение клиента", "calls": [номера], '
    '"handled": "well|partly|badly", "better_answer": "как лучше ответить"}], '
    '"strengths": ["что получается хорошо"], '
    '"recommendations": ["конкретные шаги на неделю, по приоритету"], '
    '"per_call": [{"n": номер, "score": 0-10, "note": "до 12 слов"}]}. '
    "Пиши сжато: до 6 ошибок, до 6 возражений, до 5 сильных сторон и шагов; "
    "per_call — по одному на каждый звонок, заметка короткая."
)


def _build_prompt(calls: list[tuple[int, Call, str | None, str | None]], focus: str | None) -> str:
    parts: list[str] = []
    total = 0
    for n, call, lead_name, rep_name in calls:
        text = _render(call.transcript)[:PER_CALL_CHARS]
        if total + len(text) > TOTAL_CHARS:
            text = text[: max(0, TOTAL_CHARS - total)]
        total += len(text)
        when = call.created_at.strftime("%d.%m %H:%M") if call.created_at else "?"
        outcome = (call.analysis or {}).get("suggested_outcome") or call.state
        if (call.talk_sec or 0) < 30 and call.talk_sec is not None:
            outcome = f"{outcome}, разговор слишком короткий для оценки"
        parts.append(
            f"=== Звонок {n} · {when} · менеджер: {rep_name or '?'} · "
            f"компания: {lead_name or '?'} · разговор {call.talk_sec or 0} с · исход: {outcome}\n{text}"
        )
    head = f"На что обратить особое внимание: {focus}\n\n" if focus else ""
    return f"{head}Звонков: {len(calls)}\n\n" + "\n\n".join(parts) + "\n\n" + _SCHEMA


def _repair_truncated(text: str) -> dict[str, Any] | None:
    """Ответ оборвался на середине — взять всё до последнего целого
    значения и закрыть открытые скобки."""
    stack: list[str] = []
    in_str = esc = False
    cuts: list[tuple[int, str]] = []
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]" and stack:
            stack.pop()
            cuts.append((i + 1, "".join(reversed(stack))))
    for pos, closers in reversed(cuts):
        try:
            data = json.loads(text[:pos] + closers)
        except ValueError:
            continue
        if isinstance(data, dict):
            return data
    return None


def _parse(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
    start = raw.find("{")
    body = raw[start:] if start >= 0 else raw
    try:
        return json.loads(body[: body.rfind("}") + 1])
    except ValueError:
        repaired = _repair_truncated(body)
        if repaired is None:
            raise
        repaired["truncated"] = True
        return repaired


async def run_review(review_id: uuid.UUID) -> None:
    """Выполнить разбор и записать итог в сессию (фоном)."""
    import anthropic

    async with session_factory() as session:
        review = await session.get(CallReview, review_id)
        if review is None:
            return
        team_id = review.team_id
        ids = [uuid.UUID(x) for x in review.call_ids]
        rows = (
            await session.execute(
                select(Call, Lead.name, User)
                .outerjoin(Lead, Lead.id == Call.lead_id)
                .outerjoin(User, User.id == Call.user_id)
                .where(Call.id.in_(ids))
                .where(Call.team_id == team_id)
                .order_by(Call.created_at)
            )
        ).all()
        focus = review.focus
    token = usage_tracker.bind_team(team_id)
    stage = usage_tracker.set_stage("calls")
    # Звонки с записью, но без расшифровки, расшифровываем сейчас: при
    # выключенной автоматике разбор — единственный, кто за неё платит.
    from leadgen.core.services.sales.telephony.processing import process_call

    for c, _lead_name, _u in rows:
        if not c.transcript and c.recording_url and c.record_consent:
            try:
                await process_call(c.id, "transcribe")
            except Exception:  # noqa: BLE001 — разберём то, что расшифровалось
                logger.warning("review %s: transcription of %s failed", review_id, c.id)
    if any(not r[0].transcript for r in rows):
        async with session_factory() as session:
            fresh = {
                c.id: c
                for c in (
                    await session.execute(select(Call).where(Call.id.in_([r[0].id for r in rows])))
                ).scalars().all()
            }
        rows = [(fresh.get(c.id, c), lead_name, u) for c, lead_name, u in rows]
    calls = [
        (n, c, lead_name, (u.display_name or u.first_name) if u else None)
        for n, (c, lead_name, u) in enumerate(
            [r for r in rows if r[0].transcript], start=1
        )
    ]
    try:
        if not calls:
            raise RuntimeError("no transcripts in the selected calls (recordings missing or transcription failed)")
        settings = get_settings()
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        msg = await usage_tracker.tracked_create(
            client,
            model=settings.anthropic_model,
            max_tokens=8000,
            system=_system(),
            messages=[{"role": "user", "content": _build_prompt(calls, focus)}],
        )
        raw = "".join(getattr(b, "text", "") for b in msg.content)
        result = _parse(raw)
        # Номера звонков в ответе → id, чтобы интерфейс открывал запись.
        result["call_map"] = {str(n): str(c.id) for n, c, _l, _r in calls}
        status, error = "done", None
    except Exception as exc:  # noqa: BLE001 — итог пишем в сессию, а не роняем воркер
        logger.exception("call review %s failed", review_id)
        result, status, error = None, "failed", str(exc)[:500]
    finally:
        usage_tracker.reset_stage(stage)
        usage_tracker.unbind_team(token)
    async with session_factory() as session:
        review = await session.get(CallReview, review_id)
        if review is not None:
            review.status = status
            review.result = result
            review.error = error
            review.finished_at = datetime.now(timezone.utc)
            await session.commit()
