from __future__ import annotations

from datetime import date
from typing import Callable

import logging

import httpx

from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories import AccountRepository, ChatRepository
from ..telegram_bot.bot import TelegramNotifier
from .insales import InsalesClient


logger = logging.getLogger(__name__)


class PaymentNotifier:
    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        telegram_notifier: TelegramNotifier,
        insales_client: InsalesClient,
    ) -> None:
        self._session_factory = session_factory
        self._telegram_notifier = telegram_notifier
        self._insales_client = insales_client

    async def notify_due_payments(self, today: date) -> None:
        async with self._session_factory() as session:
            account_repo = AccountRepository(session)
            chat_repo = ChatRepository(session)

            accounts = await account_repo.list_accounts()
            if not accounts:
                return

            chats = await chat_repo.list_chats()
            if not chats:
                return

            for account in accounts:
                if not account.notifications_enabled:
                    continue

                # Refresh paid_till from InSales before evaluating deadlines
                try:
                    info = await self._insales_client.fetch_account(
                        domain=account.shop_domain,
                        api_key=account.api_key,
                        password=account.api_password,
                    )
                except (httpx.HTTPError, ValueError) as exc:
                    logger.warning(
                        "Не удалось обновить данные аккаунта %s: %s",
                        account.shop_domain,
                        exc,
                    )
                    continue

                if info.paid_till != account.paid_till:
                    account = await account_repo.update_paid_till(account, info.paid_till)

                if not account.paid_till:
                    continue

                days_left = (account.paid_till - today).days
                if days_left < 0:
                    if account.last_notified_at == today:
                        continue
                    message = (
                        f"⚠️ Тариф аккаунта {account.title} истёк {account.paid_till:%d.%m.%Y}."
                        " Требуется продление."
                    )
                elif 0 <= days_left <= 7:
                    if account.last_notified_at == today:
                        continue
                    if days_left > 0:
                        message = (
                            f"⏰ Аккаунт {account.title} оплачен до {account.paid_till:%d.%m.%Y}."
                            f" Осталось {days_left} дн."
                        )
                    else:
                        message = (
                            f"⏰ Аккаунт {account.title} оплачен до {account.paid_till:%d.%m.%Y}."
                            " Оплата требуется сегодня!"
                        )
                else:
                    continue

                await self._telegram_notifier.broadcast_message(message, chats)
                await account_repo.update_last_notified(account, today)
