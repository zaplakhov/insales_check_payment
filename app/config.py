from __future__ import annotations

import os
from datetime import time
from pathlib import Path
from typing import Dict, Optional, Union
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseSettings, Field, validator


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    # General
    app_name: str = Field(default="Insales Payment Monitor")
    database_url: str = Field(default="sqlite+aiosqlite:///" + str(Path("data/database.db").absolute()))

    # Telegram
    telegram_bot_token: str = Field(..., env="TELEGRAM_BOT_TOKEN")

    # Notification settings
    notification_time: time = Field(default=time(hour=9, minute=0), env="NOTIFICATION_TIME")
    timezone: ZoneInfo = Field(default_factory=lambda: ZoneInfo("UTC"), env="TIMEZONE")

    quiet_hours_start: Optional[time] = Field(default=None, env="QUIET_HOURS_START")
    quiet_hours_end: Optional[time] = Field(default=None, env="QUIET_HOURS_END")

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
    def _validate_timezone(cls, value: Union[str, ZoneInfo, None]) -> ZoneInfo:
        if isinstance(value, ZoneInfo):
            return value
        if value in (None, ""):
            return ZoneInfo("UTC")
        try:
            return ZoneInfo(str(value))
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown timezone: {value}") from exc

    @validator("quiet_hours_end")
    def _validate_quiet_hours(
        cls,
        end: Optional[time],
        values: Dict[str, Optional[time]],
    ) -> Optional[time]:
        start = values.get("quiet_hours_start")
        if start is None and end is None:
            return None
        if start is None or end is None:
            raise ValueError("Both QUIET_HOURS_START and QUIET_HOURS_END must be set to enable quiet hours.")
        return end


settings = Settings()
