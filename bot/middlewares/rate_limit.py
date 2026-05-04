from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import TypeVar

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)
HandlerResult = TypeVar("HandlerResult")


async def is_rate_limited(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    settings = context.application.bot_data.get("settings")
    min_interval_seconds = getattr(settings, "rate_limit_seconds", 1)
    if min_interval_seconds <= 0 or update.effective_user is None:
        return False

    user_id = update.effective_user.id
    now = time.monotonic()
    last_seen: dict[int, float] = context.application.bot_data.setdefault("rate_limit_last_seen", {})
    elapsed = now - last_seen.get(user_id, 0)

    if elapsed < min_interval_seconds:
        logger.info("Rate limited user_id=%s elapsed=%.3f", user_id, elapsed)
        if update.effective_message is not None:
            await update.effective_message.reply_text("⏳ Слишком часто. Попробуйте через секунду.")
        return True

    last_seen[user_id] = now
    return False


def rate_limited(
    handler: Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[HandlerResult]],
) -> Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[HandlerResult | None]]:
    @wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> HandlerResult | None:
        if await is_rate_limited(update, context):
            return None
        return await handler(update, context)

    return wrapper
