from __future__ import annotations

from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import settings
from .services.notifier import PaymentNotifier


class Scheduler:
    def __init__(self, notifier: PaymentNotifier) -> None:
        self._notifier = notifier
        self._scheduler = AsyncIOScheduler(timezone=settings.timezone)

    async def start(self) -> None:
        trigger = CronTrigger(
            hour=settings.notification_time.hour,
            minute=settings.notification_time.minute,
            timezone=settings.timezone,
        )
        self._scheduler.add_job(self._run_notifications, trigger)
        self._scheduler.start()

    async def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    async def _run_notifications(self) -> None:
        today = datetime.now(self._scheduler.timezone).date()
        await self._notifier.notify_due_payments(today)
