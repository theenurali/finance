from __future__ import annotations

import logging
import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from bot.keyboards.common import build_main_menu_keyboard, build_reset_confirmation_keyboard
from bot.middlewares.rate_limit import rate_limited
from database.db import sessionmanager
from database.queries import (
    count_transactions,
    create_debt,
    create_user_if_not_exists,
    delete_user_transactions,
    delete_budget,
    get_daily_expenses,
    get_debt_summary,
    get_expense_total_between,
    get_month_transactions,
    get_top_expense_categories,
    get_user_summary,
    list_active_budgets,
    list_transactions,
    list_active_debts,
    mark_debt_paid,
    upsert_budget,
)
from services.analytics import build_budget_report, build_month_report, build_overall_stats, get_top_category
from services.reports import build_csv_export
from utils.constants import MENU_BUDGET, MENU_DAY, MENU_DEBT, MENU_HISTORY, MENU_MONTH, MENU_STATS
from utils.helpers import escape_md, format_money, parse_amount, render_transactions_page

logger = logging.getLogger(__name__)


async def _get_session(context: ContextTypes.DEFAULT_TYPE) -> AsyncSession:
    return context.application.bot_data["session_factory"]()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return

    try:
        async with await _get_session(context) as session:
            await create_user_if_not_exists(
                session=session,
                telegram_id=update.effective_user.id,
                username=update.effective_user.username,
                first_name=update.effective_user.first_name,
            )
            await session.commit()

        text = (
            "💰 *Finance Bot готов к работе*\n\n"
            "Я помогу учитывать доходы и расходы. Каждый пользователь видит только свои данные.\n\n"
            "*Быстрый ввод:*\n"
            "`/add 2000 еда`\n"
            "`/income 5000 зарплата`\n\n"
            "*Команды:*\n"
            "/add — добавить расход\n"
            "/income — добавить доход\n"
            "/stats — общая статистика\n"
            "/month — отчет за месяц\n"
            "/day — расходы за сегодня\n"
            "/top — топ категория\n"
            "/budget — бюджет на период\n"
            "/debt — долги\n"
            "/export — CSV выгрузка\n"
            "/reset — очистить мои данные\n\n"
            "Снизу теперь главное меню: расход, доход, долги, бюджет и отчеты."
        )
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=build_main_menu_keyboard(),
        )
    except Exception:
        logger.exception("Failed to handle /start for user_id=%s", update.effective_user.id)
        await update.message.reply_text("⚠️ Не удалось запустить бота. Попробуйте позже.")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return

    try:
        async with await _get_session(context) as session:
            await create_user_if_not_exists(session, update.effective_user.id)
            summary = await get_user_summary(session, update.effective_user.id)
            top_categories = await get_top_expense_categories(session, update.effective_user.id, limit=1)

        report = build_overall_stats(summary, top_categories)
        await update.message.reply_text(report, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        logger.exception("Failed to handle /stats for user_id=%s", update.effective_user.id)
        await update.message.reply_text("⚠️ Не удалось получить статистику.")


async def month(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return

    try:
        async with await _get_session(context) as session:
            await create_user_if_not_exists(session, update.effective_user.id)
            transactions = await get_month_transactions(session, update.effective_user.id)

        report = build_month_report(transactions)
        await update.message.reply_text(report, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        logger.exception("Failed to handle /month for user_id=%s", update.effective_user.id)
        await update.message.reply_text("⚠️ Не удалось собрать месячный отчет.")


async def day(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return

    try:
        async with await _get_session(context) as session:
            await create_user_if_not_exists(session, update.effective_user.id)
            transactions = await get_daily_expenses(session, update.effective_user.id)

        total = sum(item.amount for item in transactions)
        if not transactions:
            await update.message.reply_text("📅 Сегодня расходов пока нет.")
            return

        lines = ["📅 *Расходы за сегодня*", ""]
        for item in transactions[:30]:
            lines.append(f"• {escape_md(item.category)} — {format_money(item.amount)}")
        if len(transactions) > 30:
            lines.append(f"\nПоказаны первые 30 из {len(transactions)} операций.")
        lines.append(f"\n*Итого:* {format_money(total)}")

        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
    except Exception:
        logger.exception("Failed to handle /day for user_id=%s", update.effective_user.id)
        await update.message.reply_text("⚠️ Не удалось получить дневной отчет.")


async def top(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return

    try:
        async with await _get_session(context) as session:
            await create_user_if_not_exists(session, update.effective_user.id)
            categories = await get_top_expense_categories(session, update.effective_user.id, limit=5)

        top_category = get_top_category(categories)
        if top_category is None:
            await update.message.reply_text("🏆 Расходов пока нет.")
            return

        lines = ["🏆 *Топ категорий расходов*", ""]
        for index, item in enumerate(categories, start=1):
            lines.append(f"{index}. {escape_md(item.category)} — {format_money(item.total)}")

        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
    except Exception:
        logger.exception("Failed to handle /top for user_id=%s", update.effective_user.id)
        await update.message.reply_text("⚠️ Не удалось получить топ категорий.")


async def budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return

    try:
        async with await _get_session(context) as session:
            await create_user_if_not_exists(session, update.effective_user.id)

            if context.args:
                action = context.args[0].lower()
                if action in {"delete", "remove", "удалить"}:
                    if len(context.args) < 2 or not context.args[1].isdigit():
                        await update.message.reply_text("Укажите ID бюджета: `/budget delete 2`", parse_mode=ParseMode.MARKDOWN)
                        return
                    deleted = await delete_budget(session, update.effective_user.id, int(context.args[1]))
                    await session.commit()
                    if deleted:
                        await update.message.reply_text("✅ Бюджет удален.")
                    else:
                        await update.message.reply_text("Не нашел бюджет с таким ID.")
                    return

                budget_data = _parse_budget_args(context.args)
                budget_model = await upsert_budget(
                    session=session,
                    user_id=update.effective_user.id,
                    amount=budget_data["amount"],
                    period_type=budget_data["period_type"],
                    title=budget_data["title"],
                    start_at=budget_data["start_at"],
                    end_at=budget_data["end_at"],
                )
                await session.commit()
                spent = await get_expense_total_between(
                    session,
                    update.effective_user.id,
                    budget_model.start_at,
                    budget_model.end_at,
                )
                report = build_budget_report(
                    title=f"Бюджет #{budget_model.id}: {budget_model.title}",
                    limit_amount=Decimal(budget_model.limit_amount),
                    spent=spent,
                    start_date=budget_model.start_at.date(),
                    end_date=budget_model.end_at.date() - timedelta(days=1),
                )
                await update.message.reply_text(f"✅ Бюджет сохранен.\n\n{report}", parse_mode=ParseMode.MARKDOWN)
                return

            budgets = await list_active_budgets(session, update.effective_user.id)
            reports = []
            for budget_model in budgets:
                spent = await get_expense_total_between(
                    session,
                    update.effective_user.id,
                    budget_model.start_at,
                    budget_model.end_at,
                )
                reports.append(
                    build_budget_report(
                        title=f"Бюджет #{budget_model.id}: {budget_model.title}",
                        limit_amount=Decimal(budget_model.limit_amount),
                        spent=spent,
                        start_date=budget_model.start_at.date(),
                        end_date=budget_model.end_at.date() - timedelta(days=1),
                    )
                )

        if not reports:
            await update.message.reply_text(
                "💼 Бюджеты пока не заданы.\n\n"
                "*Примеры:*\n"
                "`/budget 120000` — лимит на текущий месяц\n"
                "`/budget day 5000` — лимит на сегодня\n"
                "`/budget day 2026-05-10 7000` — лимит на дату\n"
                "`/budget month 2026-05 150000` — лимит на месяц\n"
                "`/budget days 10 40000` — лимит на 10 дней\n"
                "`/budget custom 2026-05-01 2026-05-15 50000`\n"
                "`/budget delete 2` — удалить бюджет",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        await update.message.reply_text("\n\n".join(reports), parse_mode=ParseMode.MARKDOWN)
    except ValueError as error:
        await update.message.reply_text(f"⚠️ {error}\n\n{_budget_help()}", parse_mode=ParseMode.MARKDOWN)
    except Exception:
        logger.exception("Failed to handle /budget for user_id=%s", update.effective_user.id)
        await update.message.reply_text("⚠️ Не удалось обработать бюджет.")


async def debt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return

    try:
        args = context.args or []
        async with await _get_session(context) as session:
            await create_user_if_not_exists(session, update.effective_user.id)

            if not args or args[0].lower() in {"list", "список"}:
                debts = await list_active_debts(session, update.effective_user.id)
                summary = await get_debt_summary(session, update.effective_user.id)
                await update.message.reply_text(_render_debts(debts, summary), parse_mode=ParseMode.MARKDOWN)
                return

            action = args[0].lower()
            if action in {"paid", "close", "закрыть", "оплачен", "погасить"}:
                if len(args) < 2 or not args[1].isdigit():
                    await update.message.reply_text("Укажите ID долга: `/debt paid 3`", parse_mode=ParseMode.MARKDOWN)
                    return
                closed = await mark_debt_paid(session, update.effective_user.id, int(args[1]))
                await session.commit()
                if closed:
                    await update.message.reply_text("✅ Долг закрыт.")
                else:
                    await update.message.reply_text("Не нашел активный долг с таким ID.")
                return

            debt_args = args[1:] if action in {"add", "добавить"} else args
            direction, amount, person, note = _parse_debt_args(debt_args)
            created = await create_debt(
                session=session,
                user_id=update.effective_user.id,
                person=person,
                amount=amount,
                direction=direction,
                note=note,
            )
            await session.commit()

        direction_text = "я должен" if direction == "i_owe" else "мне должны"
        await update.message.reply_text(
            f"✅ Долг добавлен: #{created.id}\n"
            f"{direction_text}: {escape_md(person)} — {format_money(amount)}",
            parse_mode=ParseMode.MARKDOWN,
        )
    except ValueError as error:
        await update.message.reply_text(f"⚠️ {error}\n\n{_debt_help()}", parse_mode=ParseMode.MARKDOWN)
    except Exception:
        logger.exception("Failed to handle /debt for user_id=%s", update.effective_user.id)
        await update.message.reply_text("⚠️ Не удалось обработать долги.")


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return

    try:
        async with await _get_session(context) as session:
            await create_user_if_not_exists(session, update.effective_user.id)
            total = await count_transactions(session, update.effective_user.id)

        if total == 0:
            await update.message.reply_text("Данных для удаления пока нет.")
            return

        await update.message.reply_text(
            f"⚠️ Удалить все ваши операции? Сейчас записей: {total}.",
            reply_markup=build_reset_confirmation_keyboard(),
        )
    except Exception:
        logger.exception("Failed to handle /reset for user_id=%s", update.effective_user.id)
        await update.message.reply_text("⚠️ Не удалось подготовить сброс данных.")


async def confirm_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.from_user is None:
        return

    await query.answer()

    try:
        if query.data == "reset:cancel":
            await query.edit_message_text("Сброс отменен.")
            return

        async with await _get_session(context) as session:
            await delete_user_transactions(session, query.from_user.id)
            await session.commit()

        await query.edit_message_text("✅ Ваши операции удалены.")
    except Exception:
        logger.exception("Failed to confirm reset for user_id=%s", query.from_user.id)
        await query.edit_message_text("⚠️ Не удалось удалить данные.")


async def export_csv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return

    try:
        await update.message.chat.send_action(ChatAction.UPLOAD_DOCUMENT)
        settings = context.application.bot_data["settings"]
        page_size = max(100, int(settings.export_page_size))
        offset = 0
        transactions = []

        async with await _get_session(context) as session:
            await create_user_if_not_exists(session, update.effective_user.id)
            while True:
                batch = await list_transactions(
                    session,
                    update.effective_user.id,
                    limit=page_size,
                    offset=offset,
                )
                transactions.extend(batch)
                if len(batch) < page_size:
                    break
                offset += page_size

        if not transactions:
            await update.message.reply_text("Экспортировать пока нечего.")
            return

        document = build_csv_export(transactions)
        await update.message.reply_document(
            document=document,
            filename="finance_export.csv",
            caption="📦 CSV выгрузка ваших операций",
        )
    except Exception:
        logger.exception("Failed to export CSV for user_id=%s", update.effective_user.id)
        await update.message.reply_text("⚠️ Не удалось сформировать CSV.")


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return

    try:
        page = 1
        if context.args:
            page = max(1, int(context.args[0]))
        page_size = 10
        offset = (page - 1) * page_size

        async with await _get_session(context) as session:
            await create_user_if_not_exists(session, update.effective_user.id)
            total = await count_transactions(session, update.effective_user.id)
            transactions = await list_transactions(
                session,
                update.effective_user.id,
                limit=page_size,
                offset=offset,
            )

        text, keyboard = render_transactions_page(transactions, page, page_size, total)
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    except ValueError:
        await update.message.reply_text("Укажите номер страницы: `/history 2`", parse_mode=ParseMode.MARKDOWN)
    except Exception:
        logger.exception("Failed to handle /history for user_id=%s", update.effective_user.id)
        await update.message.reply_text("⚠️ Не удалось получить историю.")


async def paginate_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.from_user is None or query.data is None:
        return

    await query.answer()

    try:
        _, page_raw = query.data.split(":", maxsplit=1)
        page = max(1, int(page_raw))
        page_size = 10
        offset = (page - 1) * page_size

        async with await _get_session(context) as session:
            total = await count_transactions(session, query.from_user.id)
            transactions = await list_transactions(
                session,
                query.from_user.id,
                limit=page_size,
                offset=offset,
            )

        text, keyboard = render_transactions_page(transactions, page, page_size, total)
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    except Exception:
        logger.exception("Failed to paginate history for user_id=%s", query.from_user.id)
        await query.edit_message_text("⚠️ Не удалось переключить страницу.")


def register_command_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("start", rate_limited(start)))
    application.add_handler(CommandHandler("stats", rate_limited(stats)))
    application.add_handler(CommandHandler("month", rate_limited(month)))
    application.add_handler(CommandHandler("day", rate_limited(day)))
    application.add_handler(CommandHandler("top", rate_limited(top)))
    application.add_handler(CommandHandler("budget", rate_limited(budget)))
    application.add_handler(CommandHandler("debt", rate_limited(debt)))
    application.add_handler(CommandHandler("reset", rate_limited(reset)))
    application.add_handler(CommandHandler("export", rate_limited(export_csv)))
    application.add_handler(CommandHandler("history", rate_limited(history)))
    application.add_handler(MessageHandler(filters.Regex(f"^{re.escape(MENU_STATS)}$"), rate_limited(stats)))
    application.add_handler(MessageHandler(filters.Regex(f"^{re.escape(MENU_MONTH)}$"), rate_limited(month)))
    application.add_handler(MessageHandler(filters.Regex(f"^{re.escape(MENU_DAY)}$"), rate_limited(day)))
    application.add_handler(MessageHandler(filters.Regex(f"^{re.escape(MENU_BUDGET)}$"), rate_limited(budget)))
    application.add_handler(MessageHandler(filters.Regex(f"^{re.escape(MENU_DEBT)}$"), rate_limited(debt)))
    application.add_handler(MessageHandler(filters.Regex(f"^{re.escape(MENU_HISTORY)}$"), rate_limited(history)))
    application.add_handler(CallbackQueryHandler(confirm_reset, pattern=r"^reset:"))
    application.add_handler(CallbackQueryHandler(paginate_history, pattern=r"^history:"))


async def shutdown_database(_: Application) -> None:
    await sessionmanager.close()


def _parse_debt_args(args: list[str]) -> tuple[str, Decimal, str, str | None]:
    if len(args) < 3:
        raise ValueError("Нужен формат долга.")

    direction_alias = args[0].lower()
    if direction_alias in {"я", "owe", "i_owe", "должен", "должна"}:
        direction = "i_owe"
    elif direction_alias in {"мне", "me", "owed", "owed_to_me", "должны"}:
        direction = "owed_to_me"
    else:
        raise ValueError("Напишите `я`, если вы должны, или `мне`, если должны вам.")

    amount = parse_amount(args[1])
    person = args[2].strip()
    if not person:
        raise ValueError("Укажите имя человека.")
    note = " ".join(args[3:]).strip() or None
    return direction, amount, person[:255], note[:500] if note else None


def _render_debts(debts: list[object], summary: tuple[Decimal, Decimal]) -> str:
    i_owe, owed_to_me = summary
    lines = [
        "🤝 *Долги*",
        "",
        f"Я должен: *{format_money(i_owe)}*",
        f"Мне должны: *{format_money(owed_to_me)}*",
        "",
    ]

    if not debts:
        lines.append("Активных долгов нет.")
        lines.append("")
        lines.append(_debt_help())
        return "\n".join(lines)

    lines.append("*Активные долги:*")
    for item in debts:
        direction = "я должен" if item.direction.value == "i_owe" else "мне должны"
        note = f" — {escape_md(item.note)}" if item.note else ""
        lines.append(f"#{item.id} {direction}: {escape_md(item.person)} — {format_money(item.amount)}{note}")

    lines.append("")
    lines.append("Закрыть долг: `/debt paid ID`")
    return "\n".join(lines)


def _debt_help() -> str:
    return (
        "*Примеры:*\n"
        "`/debt я 5000 Али обед`\n"
        "`/debt мне 10000 Данияр заем`\n"
        "`/debt list`\n"
        "`/debt paid 3`"
    )


def _parse_budget_args(args: list[str]) -> dict[str, object]:
    if not args:
        raise ValueError("Нужен период и сумма бюджета.")

    action = args[0].lower()
    today = date.today()

    if _looks_like_amount(action):
        amount = parse_amount(args[0])
        start_at, end_at = _month_bounds(today.year, today.month)
        return {
            "amount": amount,
            "period_type": "month",
            "title": f"месяц {today.strftime('%m.%Y')}",
            "start_at": start_at,
            "end_at": end_at,
        }

    if action in {"day", "день"}:
        if len(args) == 2:
            target_date = today
            amount = parse_amount(args[1])
        elif len(args) >= 3:
            target_date = _parse_date(args[1])
            amount = parse_amount(args[2])
        else:
            raise ValueError("Для дневного бюджета нужна сумма.")

        start_at = datetime.combine(target_date, time.min)
        end_at = start_at + timedelta(days=1)
        return {
            "amount": amount,
            "period_type": "day",
            "title": f"день {target_date.strftime('%d.%m.%Y')}",
            "start_at": start_at,
            "end_at": end_at,
        }

    if action in {"month", "месяц"}:
        if len(args) == 2:
            target_year, target_month = today.year, today.month
            amount = parse_amount(args[1])
        elif len(args) >= 3:
            target_year, target_month = _parse_month(args[1])
            amount = parse_amount(args[2])
        else:
            raise ValueError("Для месячного бюджета нужна сумма.")

        start_at, end_at = _month_bounds(target_year, target_month)
        return {
            "amount": amount,
            "period_type": "month",
            "title": f"месяц {target_month:02d}.{target_year}",
            "start_at": start_at,
            "end_at": end_at,
        }

    if action in {"days", "дней", "period", "период"}:
        if len(args) < 3:
            raise ValueError("Для периода укажите количество дней и сумму.")
        try:
            days = int(args[1])
        except ValueError as error:
            raise ValueError("Количество дней должно быть числом.") from error
        if days <= 0 or days > 366:
            raise ValueError("Количество дней должно быть от 1 до 366.")
        amount = parse_amount(args[2])
        start_at = datetime.combine(today, time.min)
        end_at = start_at + timedelta(days=days)
        return {
            "amount": amount,
            "period_type": "custom",
            "title": f"{days} дней с {today.strftime('%d.%m.%Y')}",
            "start_at": start_at,
            "end_at": end_at,
        }

    if action in {"custom", "range", "с", "период-с"}:
        if len(args) < 4:
            raise ValueError("Для custom укажите дату начала, дату конца и сумму.")
        start_date = _parse_date(args[1])
        end_date = _parse_date(args[2])
        if end_date < start_date:
            raise ValueError("Дата конца не может быть раньше даты начала.")
        amount = parse_amount(args[3])
        start_at = datetime.combine(start_date, time.min)
        end_at = datetime.combine(end_date, time.min) + timedelta(days=1)
        return {
            "amount": amount,
            "period_type": "custom",
            "title": f"{start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}",
            "start_at": start_at,
            "end_at": end_at,
        }

    raise ValueError("Не понял период бюджета.")


def _parse_date(raw_value: str) -> date:
    for date_format in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(raw_value, date_format).date()
        except ValueError:
            continue
    raise ValueError("Дата должна быть в формате YYYY-MM-DD или DD.MM.YYYY.")


def _parse_month(raw_value: str) -> tuple[int, int]:
    for month_format in ("%Y-%m", "%m.%Y"):
        try:
            parsed = datetime.strptime(raw_value, month_format)
            return parsed.year, parsed.month
        except ValueError:
            continue
    raise ValueError("Месяц должен быть в формате YYYY-MM или MM.YYYY.")


def _month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    start_at = datetime(year=year, month=month, day=1)
    if month == 12:
        end_at = datetime(year=year + 1, month=1, day=1)
    else:
        end_at = datetime(year=year, month=month + 1, day=1)
    return start_at, end_at


def _looks_like_amount(raw_value: str) -> bool:
    try:
        parse_amount(raw_value)
    except ValueError:
        return False
    return True


def _budget_help() -> str:
    return (
        "*Примеры:*\n"
        "`/budget 120000` — текущий месяц\n"
        "`/budget day 5000` — сегодня\n"
        "`/budget day 2026-05-10 7000` — конкретная дата\n"
        "`/budget month 2026-05 150000` — месяц\n"
        "`/budget days 10 40000` — следующие 10 дней\n"
        "`/budget custom 2026-05-01 2026-05-15 50000`\n"
        "`/budget delete 2`"
    )
