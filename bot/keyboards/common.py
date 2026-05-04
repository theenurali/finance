from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from utils.constants import (
    CATEGORIES,
    MENU_BUDGET,
    MENU_DAY,
    MENU_DEBT,
    MENU_EXPENSE,
    MENU_HISTORY,
    MENU_INCOME,
    MENU_MONTH,
    MENU_STATS,
)


def build_main_menu_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(MENU_EXPENSE), KeyboardButton(MENU_INCOME)],
        [KeyboardButton(MENU_DEBT), KeyboardButton(MENU_BUDGET)],
        [KeyboardButton(MENU_MONTH), KeyboardButton(MENU_STATS)],
        [KeyboardButton(MENU_DAY), KeyboardButton(MENU_HISTORY)],
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, input_field_placeholder="Выберите действие")


def build_categories_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(CATEGORIES[0]), KeyboardButton(CATEGORIES[1])],
        [KeyboardButton(CATEGORIES[2]), KeyboardButton(CATEGORIES[3])],
        [KeyboardButton(CATEGORIES[4])],
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, input_field_placeholder="2000 еда")


def build_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Сохранить", callback_data="transaction:confirm"),
                InlineKeyboardButton("❌ Отмена", callback_data="transaction:cancel"),
            ]
        ]
    )


def build_reset_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Да, удалить", callback_data="reset:confirm"),
                InlineKeyboardButton("Отмена", callback_data="reset:cancel"),
            ]
        ]
    )


def build_pagination_keyboard(page: int, has_previous: bool, has_next: bool) -> InlineKeyboardMarkup | None:
    buttons: list[InlineKeyboardButton] = []
    if has_previous:
        buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"history:{page - 1}"))
    if has_next:
        buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"history:{page + 1}"))
    if not buttons:
        return None
    return InlineKeyboardMarkup([buttons])
