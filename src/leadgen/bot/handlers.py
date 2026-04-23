from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timezone
from html import escape as html_escape

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.analysis import AIAnalyzer
from leadgen.bot.diagnostics import format_results, run_all_checks
from leadgen.bot.keyboards import (
    AI_NICHE_CALLBACK_PREFIX,
    AI_NICHE_REDO_CALLBACK,
    BALANCE_BTN,
    CANCEL_BTN,
    CONFIRM_BTN,
    CUSTOM_NICHE_CALLBACK,
    NICHE_CALLBACK_PREFIX,
    PROFILE_BTN,
    PROFILE_EDIT_PREFIX,
    REGION_CUSTOM_CALLBACK,
    REGION_DEFAULT_CALLBACK,
    SEARCH_BTN,
    ai_niche_picker,
    confirm_menu,
    main_menu,
    niche_picker,
    profile_edit_menu,
    region_picker,
    remove_menu,
)
from leadgen.bot.states import OnboardingStates, ProfileEditStates, SearchStates
from leadgen.db.models import SearchQuery, User
from leadgen.pipeline import run_search

logger = logging.getLogger(__name__)

router = Router(name="main")

# Keep strong references to background tasks so the GC doesn't cancel them.
_background_tasks: set[asyncio.Task] = set()

MAX_NICHES = 10
MAX_NICHE_LEN = 80


WELCOME_TEXT = (
    "👋 <b>Привет!</b> Это умный бот для поиска клиентов в B2B.\n\n"
    "Ты задаёшь ниши и регион, а я собираю до 50 компаний и делаю "
    "по каждой мини-аудит: сайт, соцсети, отзывы, контакты и AI-рекомендации "
    "как тебе зайти в диалог.\n\n"
    "Сначала коротко познакомимся — так я смогу давать рекомендации именно "
    "под твою услугу и твой город."
)

ONBOARDING_PROFESSION_PROMPT = (
    "1/3. <b>Чем ты занимаешься?</b>\n\n"
    "Опиши одним сообщением — кто ты и какую услугу/продукт продаёшь. "
    "Чем конкретнее — тем полезнее будут рекомендации.\n\n"
    "Примеры:\n"
    "• «Веб-разработчик, делаю сайты под ключ для малого бизнеса»\n"
    "• «SMM-агентство, ведём Instagram и таргет для локального бизнеса»\n"
    "• «Handyman, мелкий ремонт в квартирах и офисах»\n"
    "• «Дизайнер интерьеров, работаю с коммерческими помещениями»"
)

ONBOARDING_REGION_PROMPT = (
    "2/3. <b>Где ты ищешь клиентов?</b>\n\n"
    "Укажи город или регион, где живёшь и куда готов выезжать / работать "
    "удалённо. Этот регион будет предлагаться по умолчанию при каждом поиске.\n\n"
    "Примеры: <i>Москва</i>, <i>Нью-Йорк</i>, <i>Алматы</i>, <i>Берлин</i>."
)

ONBOARDING_NICHES_PROMPT = (
    "3/3. <b>Какие ниши бизнесов тебе интересны?</b>\n\n"
    "Перечисли через запятую 3–7 ниш — именно этих клиентов я буду искать "
    "чаще всего. Позже можно добавить или заменить.\n\n"
    "Примеры:\n"
    "• «стоматологии, салоны красоты, фитнес-клубы, автосервисы»\n"
    "• «рестораны, кафе, пекарни»\n"
    "• «юридические фирмы, бухгалтерские услуги, риэлторы»"
)


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
    return (
        "👤 <b>Твой профиль</b>\n\n"
        f"<b>Чем занимаешься:</b>\n{html_escape(user.profession or '—')}\n\n"
        f"<b>Регион по умолчанию:</b> {html_escape(user.home_region or '—')}\n\n"
        f"<b>Интересные ниши:</b>\n{html_escape(niches)}"
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
        await message.answer(
            f"👋 С возвращением, <b>{html_escape(user.first_name or 'друг')}</b>!\n\n"
            "Нажми «🔎 Найти клиентов», чтобы запустить новый поиск, "
            "или «👤 Мой профиль» — посмотреть и изменить настройки.",
            reply_markup=main_menu(),
        )
        return

    await message.answer(WELCOME_TEXT, reply_markup=remove_menu())
    await message.answer(ONBOARDING_PROFESSION_PROMPT)
    await state.set_state(OnboardingStates.waiting_profession)


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


@router.message(OnboardingStates.waiting_profession, F.text)
async def onboarding_profession(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if len(text) < 5 or len(text) > 500:
        await message.answer(
            "Опиши от 5 до 500 символов — пару предложений о себе. Попробуй ещё раз."
        )
        return
    await state.update_data(profession=text)
    await message.answer(ONBOARDING_REGION_PROMPT)
    await state.set_state(OnboardingStates.waiting_home_region)


@router.message(OnboardingStates.waiting_home_region, F.text)
async def onboarding_region(message: Message, state: FSMContext) -> None:
    region = (message.text or "").strip()
    if len(region) < 2 or len(region) > 100:
        await message.answer("Регион должен быть от 2 до 100 символов. Попробуй ещё раз.")
        return
    await state.update_data(home_region=region)
    await message.answer(ONBOARDING_NICHES_PROMPT)
    await state.set_state(OnboardingStates.waiting_niches)


@router.message(OnboardingStates.waiting_niches, F.text)
async def onboarding_niches(
    message: Message, state: FSMContext, session: AsyncSession, user: User
) -> None:
    niches = _parse_niches(message.text or "")
    if not niches:
        await message.answer(
            "Не получилось распознать ниши. Перечисли 3–7 штук через запятую, "
            "каждая от 2 до 80 символов. Попробуй ещё раз."
        )
        return

    data = await state.get_data()
    user.profession = data.get("profession")
    user.service_description = data.get("profession")  # short+long share same text for MVP
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


@router.callback_query(F.data.startswith(PROFILE_EDIT_PREFIX))
async def profile_edit_start(callback: CallbackQuery, state: FSMContext) -> None:
    msg = await _callback_message(callback)
    if msg is None:
        return
    field = (callback.data or "").removeprefix(PROFILE_EDIT_PREFIX)
    await callback.answer()

    if field == "profession":
        await state.set_state(ProfileEditStates.waiting_profession)
        await msg.answer(
            "Ок, пришли новое описание того, чем ты занимаешься "
            "(5–500 символов)."
        )
    elif field == "home_region":
        await state.set_state(ProfileEditStates.waiting_home_region)
        await msg.answer("Ок, пришли новый регион по умолчанию (2–100 символов).")
    elif field == "niches":
        await state.set_state(ProfileEditStates.waiting_niches)
        await msg.answer("Ок, пришли новый список ниш через запятую (3–7 штук).")


@router.message(ProfileEditStates.waiting_profession, F.text)
async def profile_edit_profession(
    message: Message, state: FSMContext, session: AsyncSession, user: User
) -> None:
    text = (message.text or "").strip()
    if len(text) < 5 or len(text) > 500:
        await message.answer("5–500 символов, попробуй ещё раз.")
        return
    user.profession = text
    user.service_description = text
    await session.commit()
    await state.clear()
    await message.answer(
        "✅ Обновил.\n\n" + _format_profile(user), reply_markup=main_menu()
    )


@router.message(ProfileEditStates.waiting_home_region, F.text)
async def profile_edit_region(
    message: Message, state: FSMContext, session: AsyncSession, user: User
) -> None:
    region = (message.text or "").strip()
    if len(region) < 2 or len(region) > 100:
        await message.answer("2–100 символов, попробуй ещё раз.")
        return
    user.home_region = region
    await session.commit()
    await state.clear()
    await message.answer(
        "✅ Обновил.\n\n" + _format_profile(user), reply_markup=main_menu()
    )


@router.message(ProfileEditStates.waiting_niches, F.text)
async def profile_edit_niches(
    message: Message, state: FSMContext, session: AsyncSession, user: User
) -> None:
    niches = _parse_niches(message.text or "")
    if not niches:
        await message.answer("Не распознал ни одной ниши, попробуй ещё раз.")
        return
    user.niches = niches
    await session.commit()
    await state.clear()
    await message.answer(
        "✅ Обновил.\n\n" + _format_profile(user), reply_markup=main_menu()
    )


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

    if user.queries_used >= user.queries_limit:
        await state.clear()
        await message.answer(
            "🚫 Лимит запросов исчерпан.",
            reply_markup=main_menu(),
        )
        return

    query = SearchQuery(user_id=user.id, niche=niche, region=region)
    session.add(query)
    user.queries_used += 1
    await session.commit()
    await session.refresh(query)

    # Snapshot user profile so background task doesn't depend on session lifetime
    user_profile = {
        "profession": user.profession,
        "service_description": user.service_description,
        "home_region": user.home_region,
        "niches": list(user.niches or []),
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

    def _on_done(t: asyncio.Task) -> None:
        _background_tasks.discard(t)
        if t.cancelled():
            logger.warning("run_search task for query %s was cancelled", query.id)
            return
        exc = t.exception()
        if exc is not None:
            logger.exception(
                "run_search task for query %s failed", query.id, exc_info=exc
            )

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
