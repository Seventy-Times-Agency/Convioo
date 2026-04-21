from __future__ import annotations

import asyncio
import logging
from html import escape as html_escape

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.bot.keyboards import (
    BALANCE_BTN,
    CANCEL_BTN,
    CONFIRM_BTN,
    SEARCH_BTN,
    confirm_menu,
    main_menu,
    remove_menu,
)
from leadgen.bot.states import SearchStates
from leadgen.db.models import SearchQuery, User
from leadgen.pipeline import run_search

logger = logging.getLogger(__name__)

router = Router(name="main")

# Keep strong references to background tasks so the GC doesn't cancel them.
_background_tasks: set[asyncio.Task] = set()


WELCOME_TEXT = (
    "👋 <b>Привет!</b> Это умный бот для поиска клиентов в B2B.\n\n"
    "Ты задаёшь <b>нишу</b> и <b>регион</b>, а я собираю до 50 компаний и делаю "
    "по каждой мини-аудит: сайт, соцсети, отзывы, контакты и AI-рекомендации "
    "как маркетологу зайти в диалог.\n\n"
    f"Нажми «{SEARCH_BTN}», и за минуту получишь готовую базу."
)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(WELCOME_TEXT, reply_markup=main_menu())


@router.message(Command("cancel"))
@router.message(F.text == CANCEL_BTN)
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Окей, отменил. Возвращаю в главное меню.", reply_markup=main_menu())


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


@router.message(F.text == SEARCH_BTN)
async def search_start(message: Message, state: FSMContext, user: User) -> None:
    if user.queries_used >= user.queries_limit:
        await message.answer(
            "🚫 У тебя закончились запросы на этот период.\n"
            "Обратись к администратору, чтобы увеличить лимит.",
            reply_markup=main_menu(),
        )
        return
    await state.set_state(SearchStates.waiting_niche)
    await message.answer(
        "Введи <b>нишу</b> — тип бизнеса, который ищем.\n"
        "Например: <i>стоматология</i>, <i>фитнес-клуб</i>, <i>автосервис</i>.",
        reply_markup=remove_menu(),
    )


@router.message(SearchStates.waiting_niche, F.text)
async def got_niche(message: Message, state: FSMContext) -> None:
    niche = (message.text or "").strip()
    if len(niche) < 2 or len(niche) > 100:
        await message.answer("Ниша должна быть от 2 до 100 символов. Попробуй ещё раз.")
        return
    await state.update_data(niche=niche)
    await state.set_state(SearchStates.waiting_region)
    await message.answer(
        "Отлично. Теперь введи <b>регион</b> — город или область.\n"
        "Например: <i>Москва</i>, <i>Санкт-Петербург</i>, <i>Алматы</i>.",
    )


@router.message(SearchStates.waiting_region, F.text)
async def got_region(message: Message, state: FSMContext) -> None:
    region = (message.text or "").strip()
    if len(region) < 2 or len(region) > 100:
        await message.answer("Регион должен быть от 2 до 100 символов. Попробуй ещё раз.")
        return
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

    await state.clear()
    assert message.chat is not None
    await message.answer(
        "🚀 Поехали! Запускаю сбор и анализ.\n\n"
        f"Запрос: «{html_escape(niche)}» / регион: «{html_escape(region)}».\n"
        "Соберу компании, оценю точки роста и пришлю готовый отчёт + Excel.",
        reply_markup=main_menu(),
    )

    task = asyncio.create_task(run_search(query.id, message.chat.id, bot))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


@router.message(SearchStates.confirming)
async def confirm_fallback(message: Message) -> None:
    await message.answer(
        f"Нажми «{CONFIRM_BTN}», чтобы запустить, или «{CANCEL_BTN}», чтобы отменить.",
        reply_markup=confirm_menu(),
    )


@router.message()
async def fallback(message: Message) -> None:
    await message.answer(
        f"Не понял команду. Нажми «{SEARCH_BTN}» или /start.",
        reply_markup=main_menu(),
    )
