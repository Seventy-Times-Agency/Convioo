from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timezone
from html import escape as html_escape
from typing import Any

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.analysis import AIAnalyzer
from leadgen.bot.diagnostics import format_results, run_all_checks
from leadgen.bot.keyboards import (
    AGE_CALLBACK_PREFIX,
    AGE_OPTIONS,
    AGE_SKIP_CALLBACK,
    AI_NICHE_CALLBACK_PREFIX,
    AI_NICHE_REDO_CALLBACK,
    BALANCE_BTN,
    BIZ_SIZE_CALLBACK_PREFIX,
    BIZ_SIZE_SKIP_CALLBACK,
    BUSINESS_SIZE_OPTIONS,
    CANCEL_BTN,
    CONFIRM_BTN,
    CUSTOM_NICHE_CALLBACK,
    NAME_EDIT_CALLBACK,
    NAME_KEEP_CALLBACK,
    NICHE_CALLBACK_PREFIX,
    PROFILE_BTN,
    PROFILE_EDIT_PREFIX,
    PROFILE_RESET_CALLBACK,
    PROFILE_RESET_CANCEL_CALLBACK,
    PROFILE_RESET_CONFIRM_CALLBACK,
    REGION_CUSTOM_CALLBACK,
    REGION_DEFAULT_CALLBACK,
    SEARCH_BTN,
    age_picker,
    ai_niche_picker,
    business_size_picker,
    confirm_menu,
    main_menu,
    name_confirm_menu,
    niche_picker,
    profile_edit_menu,
    profile_reset_confirm_menu,
    region_picker,
    remove_menu,
)
from leadgen.bot.states import (
    OnboardingStates,
    ProfileEditStates,
    ProfileResetStates,
    SearchStates,
)
from leadgen.core.services import BillingService
from leadgen.db.models import SearchQuery, User
from leadgen.pipeline import run_search
from leadgen.utils.metrics import (
    active_background_tasks,
    rate_limited_total,
)
from leadgen.utils.rate_limit import search_limiter

logger = logging.getLogger(__name__)

router = Router(name="main")

# Keep strong references to background tasks so the GC doesn't cancel them.
_background_tasks: set[asyncio.Task] = set()

MAX_NICHES = 10
MAX_NICHE_LEN = 80


TOTAL_ONBOARDING_STEPS = 6

WELCOME_TEXT = (
    "👋 <b>Привет!</b> Я — умный бот для поиска B2B-клиентов.\n\n"
    "Как это работает: ты описываешь нишу и регион, а я собираю до 50 компаний "
    "и делаю по каждой мини-аудит — сайт, соцсети, отзывы, контакты и "
    "AI-рекомендации как к ним заходить.\n\n"
    "Чтобы советы были реально под тебя, давай коротко познакомимся — "
    f"это {TOTAL_ONBOARDING_STEPS} быстрых шагов. В любой момент можно нажать "
    f"<b>{CANCEL_BTN}</b> и вернуться позже."
)

ONBOARDING_NAME_PROMPT_TEMPLATE = (
    "<b>Шаг 1/{total}. Как мне к тебе обращаться?</b>\n\n"
    "Telegram подсказывает, что тебя зовут <b>{name}</b>. Оставим так, "
    "или предложишь другое имя?"
)

ONBOARDING_NAME_PROMPT_NO_TG = (
    f"<b>Шаг 1/{TOTAL_ONBOARDING_STEPS}. Как мне к тебе обращаться?</b>\n\n"
    "Напиши имя или никнейм, которым я буду тебя называть (2–40 символов)."
)

ONBOARDING_AGE_PROMPT = (
    f"<b>Шаг 2/{TOTAL_ONBOARDING_STEPS}. Сколько тебе лет?</b>\n\n"
    "Это помогает подбирать стиль питча и целевой сегмент. "
    "Нажми кнопку или пропусти."
)

ONBOARDING_BUSINESS_SIZE_PROMPT = (
    f"<b>Шаг 3/{TOTAL_ONBOARDING_STEPS}. Какой у тебя формат бизнеса?</b>\n\n"
    "От масштаба твоей команды зависит, с какими по размеру клиентами "
    "имеет смысл работать и какой нужен питч."
)

ONBOARDING_PROFESSION_PROMPT = (
    f"<b>Шаг 4/{TOTAL_ONBOARDING_STEPS}. Чем ты занимаешься?</b>\n\n"
    "Опиши одним сообщением — кто ты и какую услугу/продукт продаёшь. "
    "Чем конкретнее — тем полезнее будут рекомендации.\n\n"
    "Примеры:\n"
    "• «Веб-разработчик, делаю сайты под ключ для малого бизнеса»\n"
    "• «SMM-агентство, ведём Instagram и таргет для локального бизнеса»\n"
    "• «Handyman, мелкий ремонт в квартирах и офисах»\n"
    "• «Дизайнер интерьеров, работаю с коммерческими помещениями»"
)

ONBOARDING_REGION_PROMPT = (
    f"<b>Шаг 5/{TOTAL_ONBOARDING_STEPS}. Где ты ищешь клиентов?</b>\n\n"
    "Укажи город или регион, где живёшь и куда готов выезжать / работать "
    "удалённо. Этот регион будет предлагаться по умолчанию при каждом поиске.\n\n"
    "Примеры: <i>Москва</i>, <i>Нью-Йорк</i>, <i>Алматы</i>, <i>Берлин</i>."
)

ONBOARDING_NICHES_PROMPT = (
    f"<b>Шаг 6/{TOTAL_ONBOARDING_STEPS}. Какие ниши бизнесов тебе интересны?</b>\n\n"
    "Напиши свободным текстом — я разберу на конкретные ниши. Можно "
    "через запятую, можно целой фразой, можно смешивать языки.\n\n"
    "Примеры (любая форма работает):\n"
    "• <i>«стоматологии, салоны красоты, фитнес-клубы, автосервисы»</i>\n"
    "• <i>«roofing, restaurants, tattoo studios»</i>\n"
    "• <i>«хочу работать с ресторанами и юристами»</i>\n"
    "• <i>«в целом любые локальные бизнесы в сфере услуг»</i>"
)


AGE_LABELS: dict[str, str] = {code: label for label, code in AGE_OPTIONS}
BUSINESS_SIZE_LABELS: dict[str, str] = {
    code: label for label, code in BUSINESS_SIZE_OPTIONS
}


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _parse_niches(raw: str) -> list[str]:
    """Split a comma/newline-separated string into a cleaned niche list."""
    parts = [p.strip() for chunk in raw.split("\n") for p in chunk.split(",")]
    cleaned: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if not part:
            continue
        if len(part) < 2 or len(part) > MAX_NICHE_LEN:
            continue
        key = part.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(part)
        if len(cleaned) >= MAX_NICHES:
            break
    return cleaned


def _is_onboarded(user: User) -> bool:
    return user.onboarded_at is not None and bool(user.profession) and bool(user.niches)


def _format_profile(user: User) -> str:
    niches = ", ".join(user.niches or []) or "—"
    age_display = AGE_LABELS.get(user.age_range or "", user.age_range) or "—"
    biz_display = (
        BUSINESS_SIZE_LABELS.get(user.business_size or "", user.business_size) or "—"
    )
    display_name = user.display_name or user.first_name or "—"
    return (
        "👤 <b>Твой профиль</b>\n\n"
        f"👋 <b>Имя:</b> {html_escape(display_name)}\n"
        f"🎂 <b>Возраст:</b> {html_escape(age_display)}\n"
        f"🏢 <b>Формат бизнеса:</b> {html_escape(biz_display)}\n"
        f"📍 <b>Регион:</b> {html_escape(user.home_region or '—')}\n\n"
        f"💼 <b>Чем занимаешься:</b>\n{html_escape(user.profession or '—')}\n\n"
        f"🏷 <b>Интересные ниши:</b>\n{html_escape(niches)}"
    )


async def _callback_message(callback: CallbackQuery) -> Message | None:
    """Return ``callback.message`` as a ``Message`` if possible.

    Telegram may deliver callbacks with an inaccessible message (e.g. old
    messages after 48h) — ``callback.message`` is then ``None`` or an
    ``InaccessibleMessage``. In that case we notify the user and let the
    caller abort.
    """
    if isinstance(callback.message, Message):
        return callback.message
    await callback.answer(
        "Это сообщение устарело, начни заново: /start",
        show_alert=True,
    )
    return None


# ──────────────────────────────────────────────────────────────────────────────
# /start + onboarding
# ──────────────────────────────────────────────────────────────────────────────


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, user: User) -> None:
    await state.clear()
    if _is_onboarded(user):
        display_name = user.display_name or user.first_name or "друг"
        await message.answer(
            f"👋 С возвращением, <b>{html_escape(display_name)}</b>!\n\n"
            "Нажми «🔎 Найти клиентов», чтобы запустить новый поиск, "
            "или «👤 Мой профиль» — посмотреть и изменить настройки.",
            reply_markup=main_menu(),
        )
        return

    await message.answer(WELCOME_TEXT, reply_markup=remove_menu())
    suggested = (user.first_name or "").strip()
    if suggested:
        await message.answer(
            ONBOARDING_NAME_PROMPT_TEMPLATE.format(
                total=TOTAL_ONBOARDING_STEPS,
                name=html_escape(suggested),
            ),
            reply_markup=name_confirm_menu(suggested),
        )
    else:
        await message.answer(ONBOARDING_NAME_PROMPT_NO_TG)
    await state.set_state(OnboardingStates.waiting_name)


@router.message(Command("cancel"))
@router.message(F.text == CANCEL_BTN)
async def cmd_cancel(message: Message, state: FSMContext, user: User) -> None:
    await state.clear()
    if _is_onboarded(user):
        await message.answer("Окей, отменил.", reply_markup=main_menu())
    else:
        await message.answer(
            "Окей, пока свернём. Напиши /start, когда будешь готов познакомиться.",
            reply_markup=remove_menu(),
        )


@router.callback_query(OnboardingStates.waiting_name, F.data == NAME_KEEP_CALLBACK)
async def onboarding_name_keep(
    callback: CallbackQuery, state: FSMContext, user: User
) -> None:
    msg = await _callback_message(callback)
    if msg is None:
        return
    suggested = (user.first_name or "").strip() or "друг"
    await state.update_data(display_name=suggested)
    await callback.answer()
    await msg.answer(f"👋 Отлично, <b>{html_escape(suggested)}</b>!")
    await msg.answer(ONBOARDING_AGE_PROMPT, reply_markup=age_picker())
    await state.set_state(OnboardingStates.waiting_age)


@router.callback_query(OnboardingStates.waiting_name, F.data == NAME_EDIT_CALLBACK)
async def onboarding_name_edit(callback: CallbackQuery) -> None:
    msg = await _callback_message(callback)
    if msg is None:
        return
    await callback.answer()
    await msg.answer("Ок, как тогда к тебе обращаться? (2–40 символов)")


@router.message(OnboardingStates.waiting_name, F.text)
async def onboarding_name_typed(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if not raw:
        await message.answer("Напиши как тебя называть.")
        return
    analyzer = AIAnalyzer()
    name = await analyzer.parse_name(raw)
    if not name or len(name) < 2 or len(name) > 40:
        await message.answer(
            "Не разобрал имя из сообщения. Напиши его просто одним словом, "
            "например: <i>Саша</i>."
        )
        return
    await state.update_data(display_name=name)
    await message.answer(f"👋 Приятно, <b>{html_escape(name)}</b>!")
    await message.answer(ONBOARDING_AGE_PROMPT, reply_markup=age_picker())
    await state.set_state(OnboardingStates.waiting_age)


@router.message(OnboardingStates.waiting_age, F.text)
async def onboarding_age_typed(message: Message, state: FSMContext) -> None:
    analyzer = AIAnalyzer()
    code = await analyzer.parse_age(message.text or "")
    if not code:
        await message.answer(
            "Не понял возраст. Нажми на кнопку выше или напиши, например: "
            "<i>мне 30</i>."
        )
        return
    await state.update_data(age_range=code)
    await message.answer(f"Ок, <b>{html_escape(AGE_LABELS.get(code, code))}</b> ✓")
    await message.answer(
        ONBOARDING_BUSINESS_SIZE_PROMPT, reply_markup=business_size_picker()
    )
    await state.set_state(OnboardingStates.waiting_business_size)


@router.message(OnboardingStates.waiting_business_size, F.text)
async def onboarding_biz_typed(message: Message, state: FSMContext) -> None:
    analyzer = AIAnalyzer()
    code = await analyzer.parse_business_size(message.text or "")
    if not code:
        await message.answer(
            "Не понял формат. Нажми на кнопку выше или напиши, например: "
            "<i>я соло</i>, <i>команда 5 человек</i>, <i>компания 30 сотрудников</i>."
        )
        return
    await state.update_data(business_size=code)
    await message.answer(
        f"Ок, <b>{html_escape(BUSINESS_SIZE_LABELS.get(code, code))}</b> ✓"
    )
    await message.answer(ONBOARDING_PROFESSION_PROMPT)
    await state.set_state(OnboardingStates.waiting_profession)


@router.callback_query(OnboardingStates.waiting_age, F.data == AGE_SKIP_CALLBACK)
async def onboarding_age_skip(callback: CallbackQuery, state: FSMContext) -> None:
    msg = await _callback_message(callback)
    if msg is None:
        return
    await state.update_data(age_range=None)
    await callback.answer()
    await msg.answer(
        ONBOARDING_BUSINESS_SIZE_PROMPT, reply_markup=business_size_picker()
    )
    await state.set_state(OnboardingStates.waiting_business_size)


@router.callback_query(OnboardingStates.waiting_age, F.data.startswith(AGE_CALLBACK_PREFIX))
async def onboarding_age_picked(callback: CallbackQuery, state: FSMContext) -> None:
    msg = await _callback_message(callback)
    if msg is None:
        return
    code = (callback.data or "").removeprefix(AGE_CALLBACK_PREFIX)
    if code not in AGE_LABELS:
        await callback.answer("Выбери один из вариантов.", show_alert=True)
        return
    await state.update_data(age_range=code)
    await callback.answer()
    await msg.answer(
        ONBOARDING_BUSINESS_SIZE_PROMPT, reply_markup=business_size_picker()
    )
    await state.set_state(OnboardingStates.waiting_business_size)


@router.callback_query(
    OnboardingStates.waiting_business_size, F.data == BIZ_SIZE_SKIP_CALLBACK
)
async def onboarding_biz_skip(callback: CallbackQuery, state: FSMContext) -> None:
    msg = await _callback_message(callback)
    if msg is None:
        return
    await state.update_data(business_size=None)
    await callback.answer()
    await msg.answer(ONBOARDING_PROFESSION_PROMPT)
    await state.set_state(OnboardingStates.waiting_profession)


@router.callback_query(
    OnboardingStates.waiting_business_size,
    F.data.startswith(BIZ_SIZE_CALLBACK_PREFIX),
)
async def onboarding_biz_picked(callback: CallbackQuery, state: FSMContext) -> None:
    msg = await _callback_message(callback)
    if msg is None:
        return
    code = (callback.data or "").removeprefix(BIZ_SIZE_CALLBACK_PREFIX)
    if code not in BUSINESS_SIZE_LABELS:
        await callback.answer("Выбери один из вариантов.", show_alert=True)
        return
    await state.update_data(business_size=code)
    await callback.answer()
    await msg.answer(ONBOARDING_PROFESSION_PROMPT)
    await state.set_state(OnboardingStates.waiting_profession)


@router.message(OnboardingStates.waiting_profession, F.text)
async def onboarding_profession(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if len(raw) < 5 or len(raw) > 500:
        await message.answer(
            "Опиши от 5 до 500 символов — пару предложений о себе. Попробуй ещё раз."
        )
        return

    thinking = await message.answer("✍️ Привожу описание в порядок...")
    try:
        analyzer = AIAnalyzer()
        clean = await analyzer.normalize_profession(raw)
    except Exception:
        logger.exception("onboarding_profession: normalize failed")
        clean = raw
    with contextlib.suppress(Exception):
        await thinking.delete()

    # Store both: the polished version drives AI prompts (profession), the
    # original is kept verbatim for the user's own reference and for
    # editing later (service_description).
    await state.update_data(profession=clean, service_description=raw)

    if clean != raw:
        await message.answer(
            "Понял тебя так:\n"
            f"<i>{html_escape(clean)}</i>\n\n"
            "Если что — потом поправим через профиль."
        )
    await message.answer(ONBOARDING_REGION_PROMPT)
    await state.set_state(OnboardingStates.waiting_home_region)


@router.message(OnboardingStates.waiting_home_region, F.text)
async def onboarding_region(message: Message, state: FSMContext) -> None:
    analyzer = AIAnalyzer()
    region = await analyzer.parse_region(message.text or "")
    if not region or len(region) < 2 or len(region) > 100:
        await message.answer(
            "Не разобрал регион. Напиши город или страну, например: "
            "<i>Москва</i>, <i>Алматы</i>, <i>Берлин</i>."
        )
        return
    await state.update_data(home_region=region)
    await message.answer(f"📍 Регион: <b>{html_escape(region)}</b> ✓")
    await message.answer(ONBOARDING_NICHES_PROMPT)
    await state.set_state(OnboardingStates.waiting_niches)


@router.message(OnboardingStates.waiting_niches, F.text)
async def onboarding_niches(
    message: Message, state: FSMContext, session: AsyncSession, user: User
) -> None:
    raw = (message.text or "").strip()

    # Free-form understanding: "Roofing стройки рестораны тату салоны"
    # should extract [roofing, стройка, рестораны, тату-салоны] without
    # forcing the user into comma-separated format. AI first, heuristic
    # comma split as fallback.
    thinking = await message.answer("🧠 Разбираю что ты ищешь на конкретные ниши...")
    try:
        analyzer = AIAnalyzer()
        intent = await analyzer.extract_search_intent(raw)
        niches = intent.get("niches") or []
    except Exception:
        logger.exception("onboarding_niches: extract_search_intent failed")
        niches = []

    # If AI returned nothing useful, try the dumb comma-split before
    # giving up — keeps old inputs like "ниша1, ниша2, ниша3" working
    # even with an LLM outage.
    if not niches:
        niches = _parse_niches(raw)

    with contextlib.suppress(Exception):
        await thinking.delete()

    if not niches:
        await message.answer(
            "Не удалось понять какие ниши ты ищешь. Попробуй переформулировать — "
            "можно писать свободно, например: "
            "<i>«стоматологии и фитнес-клубы»</i> или "
            "<i>«roofing, restaurants, tattoo studios»</i>."
        )
        return

    niches = niches[:MAX_NICHES]

    data = await state.get_data()
    user.display_name = data.get("display_name") or user.first_name
    user.age_range = data.get("age_range")
    user.business_size = data.get("business_size")
    # ``profession`` is the AI-polished version used in every lead analysis
    # prompt; ``service_description`` keeps the user's original phrasing
    # so they can see/edit exactly what they typed.
    user.profession = data.get("profession")
    user.service_description = data.get("service_description") or data.get("profession")
    user.home_region = data.get("home_region")
    user.niches = niches
    user.onboarded_at = datetime.now(timezone.utc)
    await session.commit()
    await state.clear()

    await message.answer(
        "✅ <b>Готово! Профиль сохранён.</b>\n\n"
        f"{_format_profile(user)}\n\n"
        "Теперь жми «🔎 Найти клиентов» — буду искать именно под твою услугу "
        "и регион, и давать AI-советы с учётом того, кто ты и что продаёшь.",
        reply_markup=main_menu(),
    )


# ──────────────────────────────────────────────────────────────────────────────
# /profile — view and edit
# ──────────────────────────────────────────────────────────────────────────────


@router.message(Command("profile"))
@router.message(F.text == PROFILE_BTN)
async def cmd_profile(message: Message, user: User) -> None:
    if not _is_onboarded(user):
        await message.answer(
            "Сначала давай познакомимся. Напиши /start.",
            reply_markup=remove_menu(),
        )
        return
    await message.answer(
        _format_profile(user) + "\n\nЧто изменить?",
        reply_markup=profile_edit_menu(),
    )


# Human-readable labels + picker fn for each field — used by the unified
# edit handler to keep per-field UX consistent.
_EDIT_PROMPTS: dict[str, dict[str, Any]] = {
    "name": {
        "title": "👋 Имя",
        "hint": (
            "Напиши, как тебе приятнее, чтобы к тебе обращались. Можно одним "
            "словом («Саша»), можно фразой — я разберу («называй меня Марк»)."
        ),
    },
    "age": {
        "title": "🎂 Возраст",
        "hint": (
            "Сколько тебе лет? Нажми на кнопку или напиши свободно — "
            "например, <i>мне 30</i> или <i>45</i>."
        ),
    },
    "business_size": {
        "title": "🏢 Формат бизнеса",
        "hint": (
            "Какого масштаба у тебя бизнес? Выбери кнопкой или опиши словами — "
            "<i>«я соло»</i>, <i>«команда 5 человек»</i>, <i>«компания на 30»</i>."
        ),
    },
    "profession": {
        "title": "💼 Чем занимаешься",
        "hint": (
            "Опиши одним-двумя предложениями кто ты и какую услугу продаёшь "
            "(5–500 символов)."
        ),
    },
    "home_region": {
        "title": "📍 Регион",
        "hint": (
            "Где ты ищешь клиентов? Напиши город или страну — можно полной "
            "фразой («живу в Алматы», «из Берлина»)."
        ),
    },
    "niches": {
        "title": "🏷 Интересные ниши",
        "hint": (
            "Какие ниши бизнесов ищем чаще всего? Перечисли 3–7 штук "
            "через запятую, или опиши свободно — я разберу на ниши."
        ),
    },
}


def _current_field_display(user: User, field: str) -> str:
    """Pretty-printed current value of a profile field for the edit prompt."""
    if field == "name":
        return user.display_name or user.first_name or "—"
    if field == "age":
        return AGE_LABELS.get(user.age_range or "", user.age_range) or "—"
    if field == "business_size":
        return (
            BUSINESS_SIZE_LABELS.get(user.business_size or "", user.business_size)
            or "—"
        )
    if field == "profession":
        return user.profession or "—"
    if field == "home_region":
        return user.home_region or "—"
    if field == "niches":
        return ", ".join(user.niches or []) or "—"
    return "—"


@router.callback_query(F.data.startswith(PROFILE_EDIT_PREFIX))
async def profile_edit_start(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
) -> None:
    msg = await _callback_message(callback)
    if msg is None:
        return
    field = (callback.data or "").removeprefix(PROFILE_EDIT_PREFIX)
    if field not in _EDIT_PROMPTS:
        await callback.answer("Неизвестное поле", show_alert=True)
        return
    await callback.answer()

    spec = _EDIT_PROMPTS[field]
    current = _current_field_display(user, field)
    prompt = (
        f"<b>{spec['title']}</b>\n"
        f"Сейчас: <i>{html_escape(current)}</i>\n\n"
        f"{spec['hint']}\n\n"
        "В любой момент можно отменить командой /cancel."
    )
    markup = None
    if field == "age":
        markup = age_picker()
    elif field == "business_size":
        markup = business_size_picker()

    await state.set_state(ProfileEditStates.editing)
    await state.update_data(field=field)
    await msg.answer(prompt, reply_markup=markup)


@router.callback_query(
    ProfileEditStates.editing, F.data.startswith(AGE_CALLBACK_PREFIX)
)
async def profile_edit_age_callback(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    """Inline picker fallback while editing age through profile_edit flow."""
    msg = await _callback_message(callback)
    if msg is None:
        return
    if callback.data == AGE_SKIP_CALLBACK:
        user.age_range = None
    else:
        code = (callback.data or "").removeprefix(AGE_CALLBACK_PREFIX)
        if code not in AGE_LABELS:
            await callback.answer("Выбери один из вариантов.", show_alert=True)
            return
        user.age_range = code
    await session.commit()
    await state.clear()
    await callback.answer("Сохранил")
    await msg.answer(
        "✅ Обновил.\n\n" + _format_profile(user), reply_markup=main_menu()
    )


@router.callback_query(
    ProfileEditStates.editing, F.data.startswith(BIZ_SIZE_CALLBACK_PREFIX)
)
async def profile_edit_biz_callback(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    msg = await _callback_message(callback)
    if msg is None:
        return
    if callback.data == BIZ_SIZE_SKIP_CALLBACK:
        user.business_size = None
    else:
        code = (callback.data or "").removeprefix(BIZ_SIZE_CALLBACK_PREFIX)
        if code not in BUSINESS_SIZE_LABELS:
            await callback.answer("Выбери один из вариантов.", show_alert=True)
            return
        user.business_size = code
    await session.commit()
    await state.clear()
    await callback.answer("Сохранил")
    await msg.answer(
        "✅ Обновил.\n\n" + _format_profile(user), reply_markup=main_menu()
    )


@router.message(ProfileEditStates.editing, F.text)
async def profile_edit_text(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    """Single text-input handler for every profile field.

    Which field the user is editing comes from FSM data; AI parsing
    normalises any free-form answer into the structured value.
    """
    data = await state.get_data()
    field: str | None = data.get("field")
    if field not in _EDIT_PROMPTS:
        await state.clear()
        await message.answer("Что-то сбилось. Открой /profile и попробуй ещё раз.")
        return

    raw = (message.text or "").strip()
    analyzer = AIAnalyzer()
    error_reply: str | None = None

    if field == "name":
        value = await analyzer.parse_name(raw)
        if not value or len(value) < 2 or len(value) > 40:
            error_reply = "Не разобрал имя. Напиши одним словом, например: <i>Саша</i>."
        else:
            user.display_name = value
    elif field == "age":
        value = await analyzer.parse_age(raw)
        if not value:
            error_reply = (
                "Не понял возраст. Нажми кнопку выше или напиши число, "
                "например <i>мне 30</i>."
            )
        else:
            user.age_range = value
    elif field == "business_size":
        value = await analyzer.parse_business_size(raw)
        if not value:
            error_reply = (
                "Не понял масштаб. Выбери кнопкой или опиши — "
                "<i>«соло»</i>, <i>«команда 5»</i>, <i>«30 сотрудников»</i>."
            )
        else:
            user.business_size = value
    elif field == "profession":
        if len(raw) < 5 or len(raw) > 500:
            error_reply = "5–500 символов — опиши пару предложений."
        else:
            clean = await analyzer.normalize_profession(raw)
            user.profession = clean
            user.service_description = raw
    elif field == "home_region":
        value = await analyzer.parse_region(raw)
        if not value or len(value) < 2 or len(value) > 100:
            error_reply = (
                "Не разобрал регион. Напиши город или страну, например: "
                "<i>Москва</i>."
            )
        else:
            user.home_region = value
    elif field == "niches":
        intent = await analyzer.extract_search_intent(raw)
        niches = intent.get("niches") or _parse_niches(raw)
        if not niches:
            error_reply = (
                "Не распознал ни одной ниши. Перечисли через запятую или "
                "опиши, кого ищешь свободно — я разберу."
            )
        else:
            user.niches = niches[:MAX_NICHES]

    if error_reply is not None:
        await message.answer(error_reply)
        return

    await session.commit()
    await state.clear()
    await message.answer(
        "✅ Обновил.\n\n" + _format_profile(user), reply_markup=main_menu()
    )


# ── Profile reset ──────────────────────────────────────────────────────────

RESET_CONFIRM_TEXT = (
    "⚠️ <b>Точно сбросить профиль?</b>\n\n"
    "Это удалит имя, возраст, формат бизнеса, профессию, регион и ниши. "
    "Потом я заново проведу с тобой короткое знакомство.\n\n"
    "История прошлых поисков останется."
)


@router.message(Command("reset"))
async def cmd_reset(message: Message, state: FSMContext) -> None:
    await state.set_state(ProfileResetStates.confirming)
    await message.answer(RESET_CONFIRM_TEXT, reply_markup=profile_reset_confirm_menu())


@router.callback_query(F.data == PROFILE_RESET_CALLBACK)
async def profile_reset_request(callback: CallbackQuery, state: FSMContext) -> None:
    msg = await _callback_message(callback)
    if msg is None:
        return
    await callback.answer()
    await state.set_state(ProfileResetStates.confirming)
    await msg.answer(RESET_CONFIRM_TEXT, reply_markup=profile_reset_confirm_menu())


@router.callback_query(F.data == PROFILE_RESET_CANCEL_CALLBACK)
async def profile_reset_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    msg = await _callback_message(callback)
    if msg is None:
        return
    await callback.answer()
    await state.clear()
    await msg.answer("Ок, ничего не трогаю.", reply_markup=main_menu())


@router.callback_query(F.data == PROFILE_RESET_CONFIRM_CALLBACK)
async def profile_reset_confirm(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    msg = await _callback_message(callback)
    if msg is None:
        return
    user.display_name = None
    user.age_range = None
    user.business_size = None
    user.profession = None
    user.service_description = None
    user.home_region = None
    user.niches = None
    user.onboarded_at = None
    await session.commit()
    await state.clear()
    await callback.answer("Сбросил")

    # Kick off fresh onboarding right away — user explicitly asked for this.
    await msg.answer(
        "🗑 <b>Профиль сброшен.</b> Давай познакомимся заново.",
        reply_markup=remove_menu(),
    )
    await msg.answer(WELCOME_TEXT)
    suggested = (user.first_name or "").strip()
    if suggested:
        await msg.answer(
            ONBOARDING_NAME_PROMPT_TEMPLATE.format(
                total=TOTAL_ONBOARDING_STEPS,
                name=html_escape(suggested),
            ),
            reply_markup=name_confirm_menu(suggested),
        )
    else:
        await msg.answer(ONBOARDING_NAME_PROMPT_NO_TG)
    await state.set_state(OnboardingStates.waiting_name)


# ──────────────────────────────────────────────────────────────────────────────
# Diagnostics
# ──────────────────────────────────────────────────────────────────────────────


@router.message(Command("diag"))
async def cmd_diag(message: Message, bot: Bot) -> None:
    """Run live integration checks (Google Places, Anthropic, DB, etc.) and report."""
    thinking = await message.answer(
        "🔧 Запускаю диагностику — проверяю Google Maps, сайты, Anthropic, БД…"
    )
    results = await run_all_checks(bot)
    text = format_results(results)
    with contextlib.suppress(Exception):
        await thinking.delete()
    await message.answer(text, disable_web_page_preview=True)


# ──────────────────────────────────────────────────────────────────────────────
# Balance
# ──────────────────────────────────────────────────────────────────────────────


@router.message(F.text == BALANCE_BTN)
async def cmd_balance(message: Message, user: User) -> None:
    remaining = max(user.queries_limit - user.queries_used, 0)
    await message.answer(
        "📊 Твой баланс:\n"
        f"Использовано запросов: <b>{user.queries_used}</b>\n"
        f"Лимит: <b>{user.queries_limit}</b>\n"
        f"Осталось: <b>{remaining}</b>",
        reply_markup=main_menu(),
    )


# ──────────────────────────────────────────────────────────────────────────────
# Search flow
# ──────────────────────────────────────────────────────────────────────────────


SEARCH_PROMPT_TEXT = (
    "Расскажи своими словами, <b>кого ищем</b>.\n\n"
    "Можно одним сообщением: тип бизнеса + город. "
    "Например: <i>«стоматологии и фитнес-клубы в Москве»</i> — "
    "я сам разберу на конкретные ниши и предложу выбрать.\n\n"
    "Или нажми на сохранённую нишу ниже 👇"
)

SEARCH_PROMPT_TEXT_NO_PROFILE = (
    "Расскажи своими словами, <b>кого ищем</b>.\n\n"
    "Например: <i>«стоматологии в Москве»</i> или "
    "<i>«хочу клиентов в стройке или бьюти, Нью-Йорк»</i>.\n"
    "Я разберу это на конкретные ниши и предложу выбрать."
)


@router.message(F.text == SEARCH_BTN)
async def search_start(message: Message, state: FSMContext, user: User) -> None:
    if not _is_onboarded(user):
        await message.answer(
            "Сначала давай познакомимся. Напиши /start.",
            reply_markup=remove_menu(),
        )
        return
    if user.queries_used >= user.queries_limit:
        await message.answer(
            "🚫 У тебя закончились запросы на этот период.\n"
            "Обратись к администратору, чтобы увеличить лимит.",
            reply_markup=main_menu(),
        )
        return

    await state.set_state(SearchStates.waiting_niche)
    niches = user.niches or []
    if niches:
        await message.answer(SEARCH_PROMPT_TEXT, reply_markup=niche_picker(niches))
    else:
        await message.answer(SEARCH_PROMPT_TEXT_NO_PROFILE)


@router.callback_query(SearchStates.waiting_niche, F.data == CUSTOM_NICHE_CALLBACK)
async def niche_custom(callback: CallbackQuery) -> None:
    msg = await _callback_message(callback)
    if msg is None:
        return
    await callback.answer()
    await msg.answer(
        "Ок, опиши своими словами — что за бизнес и где ищем. "
        "Я разберу на конкретные ниши."
    )


@router.callback_query(SearchStates.waiting_niche, F.data.startswith(NICHE_CALLBACK_PREFIX))
async def niche_picked(
    callback: CallbackQuery, state: FSMContext, user: User
) -> None:
    msg = await _callback_message(callback)
    if msg is None:
        return
    raw = (callback.data or "").removeprefix(NICHE_CALLBACK_PREFIX)
    niches = user.niches or []
    try:
        idx = int(raw)
        niche = niches[idx]
    except (ValueError, IndexError):
        await callback.answer("Эта ниша больше недоступна, впиши вручную.", show_alert=True)
        return
    await callback.answer()
    # Profile niches are already specific, skip AI extraction.
    await _advance_to_region(msg, state, user, niche, preset_region=None)


@router.message(SearchStates.waiting_niche, F.text)
async def niche_typed(message: Message, state: FSMContext, user: User) -> None:
    text = (message.text or "").strip()
    if len(text) < 2 or len(text) > 500:
        await message.answer(
            "От 2 до 500 символов, опиши запрос поподробнее — или короче."
        )
        return

    thinking = await message.answer("🧠 Разбираю твой запрос на конкретные ниши...")
    try:
        analyzer = AIAnalyzer()
        intent = await analyzer.extract_search_intent(text)
    except Exception:
        logger.exception("extract_search_intent failed in handler")
        intent = {"niches": [], "region": None}

    with contextlib.suppress(Exception):
        await thinking.delete()

    niches = intent.get("niches") or []
    region = intent.get("region")

    if not niches:
        await message.answer(
            "Не смог выделить ниши из запроса. Сформулируй конкретнее — "
            "тип бизнеса и город. Например: <i>«стоматологии в Москве»</i>."
        )
        return

    if len(niches) == 1:
        await _advance_to_region(message, state, user, niches[0], preset_region=region)
        return

    await state.update_data(ai_niches=niches, ai_region=region)
    await state.set_state(SearchStates.choosing_ai_niche)

    region_hint = (
        f" Регион из запроса: <b>{html_escape(region)}</b>." if region else ""
    )
    await message.answer(
        f"Вижу {len(niches)} ниш в запросе.{region_hint}\n"
        "Выбери, с какой начать — каждый запуск это отдельный запрос из "
        "твоего лимита:",
        reply_markup=ai_niche_picker(niches),
    )


@router.callback_query(
    SearchStates.choosing_ai_niche, F.data.startswith(AI_NICHE_CALLBACK_PREFIX)
)
async def ai_niche_picked(
    callback: CallbackQuery, state: FSMContext, user: User
) -> None:
    msg = await _callback_message(callback)
    if msg is None:
        return
    if callback.data == AI_NICHE_REDO_CALLBACK:
        await callback.answer()
        await state.set_state(SearchStates.waiting_niche)
        await msg.answer(
            "Ок, переформулируй запрос — одним сообщением опиши кого ищем."
        )
        return

    raw = (callback.data or "").removeprefix(AI_NICHE_CALLBACK_PREFIX)
    data = await state.get_data()
    ai_niches: list[str] = data.get("ai_niches") or []
    ai_region: str | None = data.get("ai_region")
    try:
        idx = int(raw)
        niche = ai_niches[idx]
    except (ValueError, IndexError):
        await callback.answer(
            "Этот вариант больше недоступен, начни поиск заново.",
            show_alert=True,
        )
        return
    await callback.answer()
    await _advance_to_region(msg, state, user, niche, preset_region=ai_region)


async def _advance_to_region(
    message: Message,
    state: FSMContext,
    user: User,
    niche: str,
    preset_region: str | None = None,
) -> None:
    await state.update_data(niche=niche)
    if preset_region:
        # AI already extracted a region from the user's free-form query;
        # skip the region step and go straight to confirmation.
        await _show_confirmation(message, state, preset_region)
        return
    await state.set_state(SearchStates.waiting_region)
    if user.home_region:
        await message.answer(
            f"Ниша: <b>{html_escape(niche)}</b>.\n"
            f"Ищем в твоём регионе <b>{html_escape(user.home_region)}</b> "
            "или уточним другой?",
            reply_markup=region_picker(user.home_region),
        )
    else:
        await message.answer(
            f"Ниша: <b>{html_escape(niche)}</b>.\n"
            "В каком регионе ищем? Введи город или область."
        )


@router.callback_query(SearchStates.waiting_region, F.data == REGION_DEFAULT_CALLBACK)
async def region_default(
    callback: CallbackQuery, state: FSMContext, user: User
) -> None:
    msg = await _callback_message(callback)
    if msg is None:
        return
    if not user.home_region:
        await callback.answer("Регион по умолчанию не задан", show_alert=True)
        return
    await callback.answer()
    await _show_confirmation(msg, state, user.home_region)


@router.callback_query(SearchStates.waiting_region, F.data == REGION_CUSTOM_CALLBACK)
async def region_custom(callback: CallbackQuery) -> None:
    msg = await _callback_message(callback)
    if msg is None:
        return
    await callback.answer()
    await msg.answer("Ок, впиши регион текстом.")


@router.message(SearchStates.waiting_region, F.text)
async def got_region(message: Message, state: FSMContext) -> None:
    region = (message.text or "").strip()
    if len(region) < 2 or len(region) > 100:
        await message.answer("Регион должен быть от 2 до 100 символов. Попробуй ещё раз.")
        return
    await _show_confirmation(message, state, region)


async def _show_confirmation(message: Message, state: FSMContext, region: str) -> None:
    data = await state.update_data(region=region)
    await state.set_state(SearchStates.confirming)
    await message.answer(
        "Проверь запрос:\n\n"
        f"🏷 Ниша: <b>{html_escape(data['niche'])}</b>\n"
        f"📍 Регион: <b>{html_escape(region)}</b>\n\n"
        "Запускаем поиск?",
        reply_markup=confirm_menu(),
    )


@router.message(SearchStates.confirming, F.text == CONFIRM_BTN)
async def confirm_search(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
) -> None:
    data = await state.get_data()
    niche: str = data.get("niche", "")
    region: str = data.get("region", "")
    if not niche or not region:
        await state.clear()
        await message.answer(
            "Что-то пошло не так, начни заново командой /start.",
            reply_markup=main_menu(),
        )
        return

    # Soft rate-limit on the "запустить поиск" action itself so a user
    # double-tapping or spamming doesn't burn their quota + our Google
    # API budget before any DB-level guard fires.
    if not search_limiter.check_and_record(user.id):
        retry = int(search_limiter.retry_after(user.id))
        rate_limited_total.labels(action="search").inc()
        await message.answer(
            f"⏳ Слишком часто запускаешь поиск. Попробуй через {retry}с.",
            reply_markup=main_menu(),
        )
        return

    # Atomic quota check — lives in BillingService so the web API uses the
    # same race-safe path. It issues UPDATE ... WHERE queries_used < limit
    # RETURNING, so two concurrent callers can't both slip past the limit.
    billing = BillingService(session)
    quota = await billing.try_consume(user.id)
    if not quota.allowed:
        await state.clear()
        await message.answer(
            "🚫 Лимит запросов исчерпан.",
            reply_markup=main_menu(),
        )
        return
    # Keep the in-memory object in sync with the write we just committed.
    user.queries_used = quota.queries_used

    query = SearchQuery(user_id=user.id, niche=niche, region=region)
    session.add(query)
    try:
        await session.commit()
    except IntegrityError:
        # Partial unique index (uq_user_active_search) says this user
        # already has an in-flight search. The transaction is rolled back
        # as a whole — including the quota bump we just made — so no
        # manual "refund" is needed (doing one here would actually drop
        # the counter below its true value).
        await session.rollback()
        # Reload the in-memory counter so the sibling /balance command
        # doesn't show a stale value until the next middleware cycle.
        user.queries_used -= 1
        await state.clear()
        await message.answer(
            "⌛️ У тебя уже идёт поиск — дождись его окончания, "
            "и можно будет запустить следующий.",
            reply_markup=main_menu(),
        )
        return
    await session.refresh(query)

    # Snapshot user profile so background task doesn't depend on session lifetime
    user_profile = {
        "display_name": user.display_name or user.first_name,
        "age_range": user.age_range,
        "business_size": user.business_size,
        "profession": user.profession,
        "service_description": user.service_description,
        "home_region": user.home_region,
        "niches": list(user.niches or []),
        # Telegram language code — drives Google Places languageCode so
        # result display names come back in a script the user reads.
        "language_code": user.language_code,
    }

    await state.clear()
    if message.chat is None:
        logger.error("confirm_search: message.chat is None, cannot run search")
        return
    chat_id = message.chat.id
    await message.answer(
        "🚀 Поехали! Запускаю сбор и анализ.\n\n"
        f"Запрос: «{html_escape(niche)}» / регион: «{html_escape(region)}».\n"
        "Соберу компании, оценю точки роста под твою услугу и пришлю отчёт + Excel.",
        reply_markup=main_menu(),
    )

    logger.info(
        "confirm_search: spawning run_search task query=%s user=%s niche=%r region=%r",
        query.id,
        user.id,
        niche,
        region,
    )
    task = asyncio.create_task(
        run_search(query.id, chat_id, bot, user_profile=user_profile)
    )
    _background_tasks.add(task)
    active_background_tasks.inc()

    def _on_done(t: asyncio.Task) -> None:
        try:
            if t.cancelled():
                logger.warning("run_search task for query %s was cancelled", query.id)
                return
            exc = t.exception()
            if exc is not None:
                logger.exception(
                    "run_search task for query %s failed", query.id, exc_info=exc
                )
        finally:
            _background_tasks.discard(t)
            active_background_tasks.dec()

    task.add_done_callback(_on_done)


@router.message(SearchStates.confirming)
async def confirm_fallback(message: Message) -> None:
    await message.answer(
        f"Нажми «{CONFIRM_BTN}», чтобы запустить, или «{CANCEL_BTN}», чтобы отменить.",
        reply_markup=confirm_menu(),
    )


@router.message()
async def fallback(message: Message, user: User) -> None:
    if not _is_onboarded(user):
        await message.answer(
            "Сначала давай познакомимся. Напиши /start.",
            reply_markup=remove_menu(),
        )
        return
    await message.answer(
        f"Не понял команду. Нажми «{SEARCH_BTN}» или /start.",
        reply_markup=main_menu(),
    )
