from telegram.ext import Application

from bot.handlers.commands import register_command_handlers
from bot.handlers.conversations import register_conversation_handlers
from bot.handlers.errors import error_handler


def register_handlers(application: Application) -> None:
    register_command_handlers(application)
    register_conversation_handlers(application)
    application.add_error_handler(error_handler)
