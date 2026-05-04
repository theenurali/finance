from __future__ import annotations

import math
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from telegram import InlineKeyboardMarkup

from utils.constants import CATEGORIES

INCOME_DEFAULT_CATEGORY = "доход"
MAX_AMOUNT = Decimal("1000000000")


def normalize_category(category: str | None) -> str:
    if not category:
        return "другое"
    normalized = category.strip().lower().replace("ё", "ё")
    if normalized in CATEGORIES:
        return normalized
    return normalized[:64] or "другое"


def parse_amount(raw_amount: str) -> Decimal:
    try:
        amount = Decimal(raw_amount.replace(",", "."))
    except InvalidOperation as error:
        raise ValueError("Сумма должна быть числом.") from error

    if amount <= 0:
        raise ValueError("Сумма должна быть больше нуля.")
    if amount > MAX_AMOUNT:
        raise ValueError("Сумма слишком большая.")
    return amount.quantize(Decimal("0.01"))


def parse_transaction_input(raw_text: str, transaction_type: str) -> dict[str, str]:
    raw_text = (raw_text or "").strip()
    if not raw_text:
        raise ValueError("Пустой ввод. Нужен формат: 2000 еда")

    match = re.match(r"^\s*(?P<amount>[0-9]+(?:[.,][0-9]{1,2})?)\s*(?P<category>.*)$", raw_text)
    if match is None:
        raise ValueError("Не вижу сумму. Нужен формат: 2000 еда")

    amount = parse_amount(match.group("amount"))

    raw_category = match.group("category").strip()
    if transaction_type == "expense":
        category = normalize_category(raw_category)
    else:
        category = normalize_category(raw_category) if raw_category else INCOME_DEFAULT_CATEGORY

    return {
        "amount": str(amount),
        "category": category,
        "type": transaction_type,
    }


def format_money(value: Decimal | int | float) -> str:
    amount = Decimal(str(value)).quantize(Decimal("0.01"))
    return f"{amount:,.2f}".replace(",", " ") + " ₸"


def escape_md(text: Any) -> str:
    return str(text).replace("_", "\\_").replace("*", "\\*").replace("`", "\\`").replace("[", "\\[")


def render_transactions_page(
    transactions: list[Any],
    page: int,
    page_size: int,
    total: int,
) -> tuple[str, InlineKeyboardMarkup | None]:
    from bot.keyboards.common import build_pagination_keyboard

    if total == 0:
        return "История операций пустая.", None

    total_pages = max(1, math.ceil(total / page_size))
    lines = [f"📜 *История операций* — страница {page}/{total_pages}", ""]

    for item in transactions:
        icon = "💰" if item.type.value == "income" else "💸"
        created = item.created_at.strftime("%d.%m.%Y %H:%M")
        lines.append(f"{icon} {created} — {format_money(item.amount)} — {escape_md(item.category)}")

    keyboard = build_pagination_keyboard(
        page=page,
        has_previous=page > 1,
        has_next=page < total_pages,
    )
    return "\n".join(lines), keyboard
