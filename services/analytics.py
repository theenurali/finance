from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from database.models import Transaction, TransactionType
from database.queries import CategoryTotalDTO, SummaryDTO
from utils.helpers import escape_md, format_money


WARNING_CATEGORY_SHARE = Decimal("40.00")


@dataclass(frozen=True)
class CategoryShare:
    category: str
    total: Decimal
    percent: Decimal


@dataclass(frozen=True)
class TrendDTO:
    current: Decimal
    previous: Decimal
    delta_percent: Decimal


def calculate_percent(part: Decimal, total: Decimal) -> Decimal:
    if total <= 0:
        return Decimal("0.00")
    return ((part / total) * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_category_shares(transactions: list[Transaction]) -> list[CategoryShare]:
    expense_total = sum((item.amount for item in transactions if item.type == TransactionType.EXPENSE), Decimal("0"))
    by_category: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))

    for item in transactions:
        if item.type == TransactionType.EXPENSE:
            by_category[item.category] += item.amount

    shares = [
        CategoryShare(category=category, total=total, percent=calculate_percent(total, expense_total))
        for category, total in by_category.items()
    ]
    return sorted(shares, key=lambda item: item.total, reverse=True)


def get_top_category(categories: list[CategoryTotalDTO] | list[CategoryShare]) -> CategoryTotalDTO | CategoryShare | None:
    if not categories:
        return None
    return max(categories, key=lambda item: item.total)


def build_warning_messages(category_shares: list[CategoryShare]) -> list[str]:
    warnings = []
    for item in category_shares:
        if item.percent >= WARNING_CATEGORY_SHARE:
            warnings.append(
                f"⚠️ Категория *{escape_md(item.category)}* занимает {item.percent}% расходов. "
                "Стоит проверить бюджет."
            )
    return warnings


def calculate_weekly_expense_trend(transactions: list[Transaction], today: date | None = None) -> TrendDTO:
    today = today or date.today()
    current_week_start = today.toordinal() - today.weekday()
    previous_week_start = current_week_start - 7

    current = Decimal("0")
    previous = Decimal("0")
    for item in transactions:
        if item.type != TransactionType.EXPENSE:
            continue
        ordinal = item.created_at.date().toordinal()
        if current_week_start <= ordinal <= today.toordinal():
            current += item.amount
        elif previous_week_start <= ordinal < current_week_start:
            previous += item.amount

    if previous <= 0:
        delta = Decimal("100.00") if current > 0 else Decimal("0.00")
    else:
        delta = calculate_percent(current - previous, previous)
    return TrendDTO(current=current, previous=previous, delta_percent=delta)


def build_overall_stats(summary: SummaryDTO, top_categories: list[CategoryTotalDTO]) -> str:
    balance = summary.total_income - summary.total_expense
    top = get_top_category(top_categories)
    top_text = f"{escape_md(top.category)} — {format_money(top.total)}" if top else "нет расходов"

    return (
        "📊 *Общая статистика*\n\n"
        f"💰 Доход: *{format_money(summary.total_income)}*\n"
        f"💸 Расход: *{format_money(summary.total_expense)}*\n"
        f"🧾 Баланс: *{format_money(balance)}*\n"
        f"🏆 Топ категория: *{top_text}*"
    )


def build_budget_report(title: str, limit_amount: Decimal, spent: Decimal, start_date: date, end_date: date) -> str:
    remaining = limit_amount - spent
    used_percent = calculate_percent(spent, limit_amount)

    if spent > limit_amount:
        status = "⚠️ Бюджет превышен. Лучше притормозить расходы до конца периода."
    elif used_percent >= Decimal("80.00"):
        status = "⚠️ Использовано больше 80% бюджета. Остаток уже небольшой."
    elif used_percent >= Decimal("60.00"):
        status = "🟡 Темп расходов средний. Следи за крупными покупками."
    else:
        status = "✅ Темп нормальный."

    return (
        f"💼 *{escape_md(title)}*\n\n"
        f"Период: {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}\n"
        f"Лимит: *{format_money(limit_amount)}*\n"
        f"Потрачено: *{format_money(spent)}*\n"
        f"Осталось: *{format_money(remaining)}*\n"
        f"Использовано: *{used_percent}%*\n\n"
        f"{status}"
    )


def build_month_report(transactions: list[Transaction]) -> str:
    if not transactions:
        return "📆 За этот месяц операций пока нет."

    total_income = sum((item.amount for item in transactions if item.type == TransactionType.INCOME), Decimal("0"))
    total_expense = sum((item.amount for item in transactions if item.type == TransactionType.EXPENSE), Decimal("0"))
    balance = total_income - total_expense
    category_shares = calculate_category_shares(transactions)
    trend = calculate_weekly_expense_trend(transactions)

    lines = [
        "📆 *Отчет за месяц*",
        "",
        f"💰 Доход: *{format_money(total_income)}*",
        f"💸 Расход: *{format_money(total_expense)}*",
        f"🧾 Баланс: *{format_money(balance)}*",
        "",
        "📊 *Категории:*",
    ]

    if category_shares:
        for item in category_shares:
            lines.append(f"• {escape_md(item.category)} — {format_money(item.total)} ({item.percent}%)")
    else:
        lines.append("Расходов пока нет.")

    lines.extend(
        [
            "",
            "📈 *Тренд расходов:*",
            f"Текущая неделя: {format_money(trend.current)}",
            f"Предыдущая неделя: {format_money(trend.previous)}",
            f"Изменение: {trend.delta_percent}%",
        ]
    )

    warnings = build_warning_messages(category_shares)
    if warnings:
        lines.append("")
        lines.extend(warnings)

    return "\n".join(lines)
