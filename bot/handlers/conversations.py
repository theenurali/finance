from __future__ import annotations

import logging
import re
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.keyboards.common import build_categories_keyboard, build_confirmation_keyboard, build_main_menu_keyboard
from bot.middlewares.rate_limit import rate_limited
from database.queries import create_transaction, create_user_if_not_exists
from utils.constants import CATEGORIES, MENU_EXPENSE, MENU_INCOME
from utils.helpers import normalize_category, parse_transaction_input

logger = logging.getLogger(__name__)

WAITING_EXPENSE, WAITING_INCOME, WAITING_CONFIRMATION = range(3)


async def _get_session(context: ContextTypes.DEFAULT_TYPE) -> AsyncSession:
    return context.application.bot_data["session_factory"]()


async def add_expense_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _start_transaction_flow(update, context, "expense")


async def add_income_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _start_transaction_flow(update, context, "income")


async def _start_transaction_flow(update: Update, context: ContextTypes.DEFAULT_TYPE, transaction_type: str) -> int:
    if update.effective_user is None or update.message is None:
        return ConversationHandler.END

    try:
        await _ensure_user(context, update.effective_user.id, update.effective_user.username, update.effective_user.first_name)

        if context.args:
            raw_text = " ".join(context.args)
            parsed = parse_transaction_input(raw_text, transaction_type)
            context.user_data["pending_transaction"] = parsed
            await update.message.reply_text(
                _build_confirmation_text(parsed),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=build_confirmation_keyboard(),
            )
            return WAITING_CONFIRMATION

        action = "расход" if transaction_type == "expense" else "доход"
        example = "2000 еда" if transaction_type == "expense" else "5000 зарплата"
        reply_markup = build_categories_keyboard() if transaction_type == "expense" else build_main_menu_keyboard()
        await update.message.reply_text(
            f"Введите {action} в формате:\n`{example}`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup,
        )
        return WAITING_EXPENSE if transaction_type == "expense" else WAITING_INCOME
    except ValueError as error:
        await update.message.reply_text(f"⚠️ {error}")
        return ConversationHandler.END
    except Exception:
        logger.exception("Failed to start transaction flow for user_id=%s", update.effective_user.id)
        await update.message.reply_text("⚠️ Не удалось начать добавление операции.")
        return ConversationHandler.END


async def receive_expense(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _receive_transaction(update, context, "expense")


async def receive_income(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _receive_transaction(update, context, "income")


async def _receive_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE, transaction_type: str) -> int:
    if update.message is None:
        return ConversationHandler.END

    try:
        raw_text = update.message.text or ""
        quick_category = context.user_data.get("quick_category")
        if transaction_type == "expense" and quick_category and len(raw_text.split()) == 1:
            raw_text = f"{raw_text} {quick_category}"

        parsed = parse_transaction_input(raw_text, transaction_type)
        context.user_data.pop("quick_category", None)
        context.user_data["pending_transaction"] = parsed
        await update.message.reply_text(
            _build_confirmation_text(parsed),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=build_confirmation_keyboard(),
        )
        return WAITING_CONFIRMATION
    except ValueError as error:
        await update.message.reply_text(f"⚠️ {error}\n\nПример: `2000 еда`", parse_mode=ParseMode.MARKDOWN)
        return WAITING_EXPENSE if transaction_type == "expense" else WAITING_INCOME
    except Exception:
        logger.exception("Failed to parse transaction input")
        await update.message.reply_text("⚠️ Не удалось обработать ввод.")
        return ConversationHandler.END


async def confirm_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None or query.from_user is None:
        return ConversationHandler.END

    await query.answer()

    try:
        if query.data == "transaction:cancel":
            context.user_data.pop("pending_transaction", None)
            await query.edit_message_text("Операция отменена.")
            return ConversationHandler.END

        pending = context.user_data.get("pending_transaction")
        if not pending:
            await query.edit_message_text("⚠️ Операция устарела. Создайте новую.")
            return ConversationHandler.END

        async with await _get_session(context) as session:
            await create_user_if_not_exists(session, query.from_user.id, query.from_user.username, query.from_user.first_name)
            await create_transaction(
                session=session,
                user_id=query.from_user.id,
                amount=Decimal(pending["amount"]),
                transaction_type=pending["type"],
                category=pending["category"],
            )
            await session.commit()

        context.user_data.pop("pending_transaction", None)
        icon = "💸" if pending["type"] == "expense" else "💰"
        await query.edit_message_text(
            f"{icon} Операция сохранена: {pending['amount']} — {pending['category']}"
        )
        if query.message is not None:
            await query.message.reply_text("Главное меню", reply_markup=build_main_menu_keyboard())
        return ConversationHandler.END
    except Exception:
        logger.exception("Failed to confirm transaction for user_id=%s", query.from_user.id)
        await query.edit_message_text("⚠️ Не удалось сохранить операцию.")
        return ConversationHandler.END


async def quick_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    text = update.message.text or ""
    category = normalize_category(text)
    if category not in CATEGORIES:
        return ConversationHandler.END

    context.user_data["quick_category"] = category
    await update.message.reply_text(
        f"Категория: {category}\nВведите сумму расхода:",
        reply_markup=build_categories_keyboard(),
    )
    return WAITING_EXPENSE


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("pending_transaction", None)
    context.user_data.pop("quick_category", None)
    if update.message is not None:
        await update.message.reply_text("Операция отменена.", reply_markup=build_main_menu_keyboard())
    return ConversationHandler.END


async def _ensure_user(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    username: str | None = None,
    first_name: str | None = None,
) -> None:
    async with await _get_session(context) as session:
        await create_user_if_not_exists(session, user_id, username, first_name)
        await session.commit()


def _build_confirmation_text(parsed: dict[str, str]) -> str:
    action = "расход" if parsed["type"] == "expense" else "доход"
    return (
        "Подтвердите операцию:\n\n"
        f"*Тип:* {action}\n"
        f"*Сумма:* {parsed['amount']}\n"
        f"*Категория:* {parsed['category']}"
    )


def register_conversation_handlers(application: Application) -> None:
    transaction_handler = ConversationHandler(
        entry_points=[
            CommandHandler("add", rate_limited(add_expense_start)),
            CommandHandler("income", rate_limited(add_income_start)),
            MessageHandler(filters.Regex(f"^{re.escape(MENU_EXPENSE)}$"), rate_limited(add_expense_start)),
            MessageHandler(filters.Regex(f"^{re.escape(MENU_INCOME)}$"), rate_limited(add_income_start)),
            MessageHandler(filters.Regex(f"^({'|'.join(CATEGORIES)})$"), rate_limited(quick_category)),
        ],
        states={
            WAITING_EXPENSE: [
                MessageHandler(filters.Regex(f"^({'|'.join(CATEGORIES)})$"), rate_limited(quick_category)),
                MessageHandler(filters.TEXT & ~filters.COMMAND, rate_limited(receive_expense)),
            ],
            WAITING_INCOME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, rate_limited(receive_income)),
            ],
            WAITING_CONFIRMATION: [
                CallbackQueryHandler(confirm_transaction, pattern=r"^transaction:"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="transaction_conversation",
        persistent=False,
    )
    application.add_handler(transaction_handler)
