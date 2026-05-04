from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any

from telegram.ext import Application, AIORateLimiter

from bot.config import get_settings
from bot.handlers import register_handlers
from bot.handlers.commands import shutdown_database
from database.db import sessionmanager
from database import models  # noqa: F401


class SecretRedactionFilter(logging.Filter):
    def __init__(self, secrets: list[str]) -> None:
        super().__init__()
        self._secrets = [secret for secret in secrets if secret]

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._redact(record.msg)
        if record.args:
            record.args = self._redact(record.args)
        return True

    def _redact(self, value: Any) -> Any:
        if isinstance(value, str):
            for secret in self._secrets:
                value = value.replace(secret, "<redacted>")
            return value
        if isinstance(value, tuple):
            return tuple(self._redact(item) for item in value)
        if isinstance(value, dict):
            return {key: self._redact(item) for key, item in value.items()}
        value_as_text = str(value)
        if any(secret in value_as_text for secret in self._secrets):
            return self._redact(value_as_text)
        return value


def setup_logging(level: str) -> None:
    settings = get_settings()
    redaction_filter = SecretRedactionFilter([settings.bot_token])
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    root_logger = logging.getLogger()
    root_logger.addFilter(redaction_filter)
    for handler in root_logger.handlers:
        handler.addFilter(redaction_filter)
    for logger_name in ("httpx", "telegram", "telegram.ext"):
        logging.getLogger(logger_name).addFilter(redaction_filter)


async def post_init(application: Application) -> None:
    settings = get_settings()
    application.bot_data["settings"] = settings
    sessionmanager.init(settings.database_url)
    await sessionmanager.create_all()
    application.bot_data["session_factory"] = sessionmanager.session_factory()


def build_application() -> Application:
    settings = get_settings()
    application = (
        Application.builder()
        .token(settings.bot_token)
        .rate_limiter(AIORateLimiter())
        .post_init(post_init)
        .post_shutdown(shutdown_database)
        .build()
    )
    register_handlers(application)
    return application


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    logger = logging.getLogger(__name__)
    logger.info("Starting finance bot")

    application = build_application()
    application.run_polling(
        allowed_updates=["message", "callback_query"],
        close_loop=False,
    )


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        logging.getLogger(__name__).info("Bot stopped")
    except Exception:
        logging.getLogger(__name__).exception("Fatal application error")
        raise
