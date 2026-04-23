from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

SEARCH_BTN = "🔎 Найти клиентов"
BALANCE_BTN = "📊 Мой баланс"
PROFILE_BTN = "👤 Мой профиль"
CONFIRM_BTN = "✅ Запустить поиск"
CANCEL_BTN = "❌ Отменить"

# Callback-data prefixes
NICHE_CALLBACK_PREFIX = "niche:"
CUSTOM_NICHE_CALLBACK = "niche:__custom__"
AI_NICHE_CALLBACK_PREFIX = "ainiche:"
AI_NICHE_REDO_CALLBACK = "ainiche:__redo__"
REGION_CALLBACK_PREFIX = "region:"
REGION_DEFAULT_CALLBACK = "region:__default__"
REGION_CUSTOM_CALLBACK = "region:__custom__"
PROFILE_EDIT_PREFIX = "profile_edit:"


def main_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text=SEARCH_BTN))
    builder.add(KeyboardButton(text=BALANCE_BTN))
    builder.add(KeyboardButton(text=PROFILE_BTN))
    builder.adjust(1, 2)
    return builder.as_markup(resize_keyboard=True)


def confirm_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text=CONFIRM_BTN))
    builder.add(KeyboardButton(text=CANCEL_BTN))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)


def remove_menu() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def niche_picker(niches: list[str]) -> InlineKeyboardMarkup:
    """Inline keyboard with user's saved niches + 'custom' option."""
    builder = InlineKeyboardBuilder()
    for i, niche in enumerate(niches):
        builder.row(
            InlineKeyboardButton(
                text=f"🏷 {niche}",
                callback_data=f"{NICHE_CALLBACK_PREFIX}{i}",
            )
        )
    builder.row(
        InlineKeyboardButton(
            text="✏️ Своя ниша",
            callback_data=CUSTOM_NICHE_CALLBACK,
        )
    )
    return builder.as_markup()


def ai_niche_picker(niches: list[str]) -> InlineKeyboardMarkup:
    """Inline keyboard with AI-extracted niches for the user to pick one.

    Each row is one niche; a final row lets the user reformulate the query.
    """
    builder = InlineKeyboardBuilder()
    for i, niche in enumerate(niches):
        builder.row(
            InlineKeyboardButton(
                text=f"🔎 {niche}",
                callback_data=f"{AI_NICHE_CALLBACK_PREFIX}{i}",
            )
        )
    builder.row(
        InlineKeyboardButton(
            text="↩️ Переформулировать",
            callback_data=AI_NICHE_REDO_CALLBACK,
        )
    )
    return builder.as_markup()


def region_picker(default_region: str | None) -> InlineKeyboardMarkup:
    """Inline keyboard that proposes the user's home region or custom entry."""
    builder = InlineKeyboardBuilder()
    if default_region:
        builder.row(
            InlineKeyboardButton(
                text=f"📍 {default_region}",
                callback_data=REGION_DEFAULT_CALLBACK,
            )
        )
    builder.row(
        InlineKeyboardButton(
            text="✏️ Другой регион",
            callback_data=REGION_CUSTOM_CALLBACK,
        )
    )
    return builder.as_markup()


def profile_edit_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✏️ Чем занимаюсь",
            callback_data=f"{PROFILE_EDIT_PREFIX}profession",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="📍 Мой регион",
            callback_data=f"{PROFILE_EDIT_PREFIX}home_region",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🏷 Интересные ниши",
            callback_data=f"{PROFILE_EDIT_PREFIX}niches",
        )
    )
    return builder.as_markup()
