from __future__ import annotations

import os
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseSettings, Field, validator


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    # General
    app_name: str = Field(default="Insales Payment Monitor")
    database_url: str = Field(default="sqlite+aiosqlite:///" + str(Path("data/database.db").absolute()))

    # Telegram
    telegram_bot_token: str = Field(..., env="TELEGRAM_BOT_TOKEN")
    super_admin_chat_id: str = Field(..., env="TELEGRAM_SUPER_ADMIN_ID")

    # Notification settings
    notification_time: time = Field(default=time(hour=9, minute=0), env="NOTIFICATION_TIME")
    timezone: ZoneInfo = Field(default_factory=lambda: ZoneInfo("UTC"), env="TIMEZONE")

    # Insales API defaults
    insales_timeout: int = Field(default=15, ge=1)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    @validator("database_url", pre=True)
    def _expand_sqlite_path(cls, value: str) -> str:
        if value.startswith("sqlite") and "///" in value and "?" not in value:
            path = value.split("///", 1)[1]
            expanded = Path(os.path.expandvars(path)).expanduser()
            return f"sqlite+aiosqlite:///{expanded}"
        return value

    @validator("timezone", pre=True)
    def _validate_timezone(cls, value: str | ZoneInfo | None) -> ZoneInfo:
        if isinstance(value, ZoneInfo):
            return value
        if value in (None, ""):
            return ZoneInfo("UTC")
        try:
            return ZoneInfo(str(value))
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown timezone: {value}") from exc

    @validator("super_admin_chat_id", pre=True)
    def _ensure_super_admin_chat_id(cls, value: str | int | None) -> str:
        if value in (None, ""):
            raise ValueError("TELEGRAM_SUPER_ADMIN_ID must be provided")
        return str(value)


settings = Settings()
