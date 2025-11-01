from __future__ import annotations

from datetime import date
from typing import Iterable, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Account, TelegramChat


class AccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_accounts(self) -> List[Account]:
        result = await self.session.execute(select(Account).order_by(Account.title))
        return list(result.scalars().all())

    async def get_account(self, account_id: int) -> Optional[Account]:
        result = await self.session.execute(select(Account).where(Account.id == account_id))
        return result.scalars().first()

    async def get_by_domain(self, shop_domain: str) -> Optional[Account]:
        result = await self.session.execute(select(Account).where(Account.shop_domain == shop_domain))
        return result.scalars().first()

    async def add_account(
        self,
        *,
        title: str,
        shop_domain: str,
        api_key: str,
        api_password: str,
        paid_till: Optional[date] = None,
    ) -> Account:
        account = Account(
            title=title,
            shop_domain=shop_domain,
            api_key=api_key,
            api_password=api_password,
            paid_till=paid_till,
        )
        self.session.add(account)
        await self.session.commit()
        await self.session.refresh(account)
        return account

    async def update_paid_till(self, account: Account, paid_till: Optional[date]) -> Account:
        account.paid_till = paid_till
        await self.session.commit()
        await self.session.refresh(account)
        return account

    async def set_notification_state(self, account: Account, enabled: bool) -> Account:
        account.notifications_enabled = enabled
        await self.session.commit()
        await self.session.refresh(account)
        return account

    async def update_last_notified(self, account: Account, notification_date: date) -> Account:
        account.last_notified_at = notification_date
        await self.session.commit()
        await self.session.refresh(account)
        return account


class ChatRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_chat(
        self,
        *,
        chat_id: str,
        username: Optional[str],
        first_name: Optional[str],
        last_name: Optional[str],
        is_admin: Optional[bool] = None,
        is_super_admin: Optional[bool] = None,
    ) -> TelegramChat:
        existing = await self.session.execute(select(TelegramChat).where(TelegramChat.chat_id == chat_id))
        chat = existing.scalars().first()
        if chat:
            chat.username = username
            chat.first_name = first_name
            chat.last_name = last_name
        else:
            chat = TelegramChat(
                chat_id=chat_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                is_admin=bool(is_admin) if is_admin is not None else False,
                is_super_admin=bool(is_super_admin) if is_super_admin is not None else False,
            )
            self.session.add(chat)
        if is_admin is not None:
            chat.is_admin = bool(is_admin)
        if is_super_admin is not None:
            chat.is_super_admin = bool(is_super_admin)
        if chat.is_super_admin and not chat.is_admin:
            chat.is_admin = True
        await self.session.commit()
        await self.session.refresh(chat)
        return chat

    async def list_chats(self) -> Iterable[TelegramChat]:
        result = await self.session.execute(select(TelegramChat))
        return list(result.scalars().all())

    async def list_admin_chats(self) -> Iterable[TelegramChat]:
        result = await self.session.execute(
            select(TelegramChat).where(TelegramChat.is_admin.is_(True))
        )
        return list(result.scalars().all())

    async def get_chat(self, chat_id: str) -> Optional[TelegramChat]:
        result = await self.session.execute(select(TelegramChat).where(TelegramChat.chat_id == chat_id))
        return result.scalars().first()

    async def set_admin_status(self, chat_id: str, is_admin: bool) -> Tuple[Optional[TelegramChat], bool]:
        result = await self.session.execute(select(TelegramChat).where(TelegramChat.chat_id == chat_id))
        chat = result.scalars().first()
        if not chat:
            return None, False
        if chat.is_super_admin:
            # Super admin always retains admin rights
            return chat, False
        chat.is_admin = is_admin
        await self.session.commit()
        await self.session.refresh(chat)
        return chat, True
