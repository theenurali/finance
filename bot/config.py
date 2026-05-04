from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    bot_token: str = Field(..., alias="BOT_TOKEN")
    database_url: str = Field("sqlite+aiosqlite:///./finance_bot.db", alias="DATABASE_URL")
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    rate_limit_seconds: int = Field(1, alias="RATE_LIMIT_SECONDS")
    export_page_size: int = Field(500, alias="EXPORT_PAGE_SIZE")

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
