from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine
from telegram.ext import Application

from .config import settings
from .database import SessionLocal, engine
from .models import Base
from .scheduler import Scheduler
from .services.insales import InsalesClient
from .services.notifier import PaymentNotifier
from .telegram_bot.bot import TelegramBot


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_database(engine)

    telegram_application = Application.builder().token(settings.telegram_bot_token).build()
    insales_client = InsalesClient()
    bot = TelegramBot(telegram_application, insales_client)
    bot.setup_handlers()

    notifier = PaymentNotifier(SessionLocal, bot.notifier, insales_client)
    scheduler = Scheduler(notifier)

    await telegram_application.initialize()
    await telegram_application.start()
    await telegram_application.updater.start_polling()
    await scheduler.start()

    try:
        yield
    finally:
        await scheduler.shutdown()
        await telegram_application.updater.stop()
        await telegram_application.stop()
        await telegram_application.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    @app.get("/health", tags=["system"])
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    return app


async def init_database(db_engine: AsyncEngine) -> None:
    if settings.database_url.startswith("sqlite"):
        db_path = settings.database_url.split("///", 1)[1].split("?", 1)[0]
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


app = create_app()
