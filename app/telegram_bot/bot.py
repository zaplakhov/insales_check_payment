from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from sqlalchemy.exc import IntegrityError

from ..database import SessionLocal
from ..repositories import AccountRepository, ChatRepository
from ..services.insales import InsalesClient

MENU_LIST_ACCOUNTS = "👁 Список аккаунтов"
MENU_ADD_ACCOUNT = "➕ Добавить аккаунт"
MENU_PAYMENT_DATES = "📅 Даты оплаты"
MENU_TOGGLE_NOTIFICATIONS = "🔔 Управление уведомлениями"

ADD_TITLE, ADD_DOMAIN, ADD_API_KEY, ADD_API_PASSWORD = range(4)


@dataclass
class TelegramNotifier:
    application: Application

    async def broadcast_message(self, text: str, chats: Iterable) -> None:
        for chat in chats:
            try:
                await self.application.bot.send_message(chat_id=chat.chat_id, text=text)
            except TelegramError:
                continue


class TelegramBot:
    def __init__(self, application: Application, insales_client: InsalesClient) -> None:
        self.application = application
        self._insales_client = insales_client
        self._notifier = TelegramNotifier(application)

    @property
    def notifier(self) -> TelegramNotifier:
        return self._notifier

    def setup_handlers(self) -> None:
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.show_help))

        add_account_conversation = ConversationHandler(
            entry_points=[
                CommandHandler("add", self.add_account_start),
                MessageHandler(filters.Regex(f"^{MENU_ADD_ACCOUNT}$"), self.add_account_start),
            ],
            states={
                ADD_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.add_account_title)],
                ADD_DOMAIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.add_account_domain)],
                ADD_API_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.add_account_api_key)],
                ADD_API_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.add_account_api_password)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)],
        )
        self.application.add_handler(add_account_conversation)

        self.application.add_handler(
            MessageHandler(filters.Regex(f"^{MENU_LIST_ACCOUNTS}$"), self.show_accounts)
        )
        self.application.add_handler(
            MessageHandler(filters.Regex(f"^{MENU_PAYMENT_DATES}$"), self.show_payment_dates)
        )
        self.application.add_handler(
            MessageHandler(filters.Regex(f"^{MENU_TOGGLE_NOTIFICATIONS}$"), self.toggle_notifications_menu)
        )
        self.application.add_handler(CallbackQueryHandler(self.handle_toggle_callback, pattern=r"^toggle:"))

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._register_chat(update)
        message = update.effective_message
        if not message:
            return
        await message.reply_text(
            "Привет! Я помогу следить за оплатой аккаунтов InSales.",
            reply_markup=self.main_menu_keyboard(),
        )

    async def show_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if not message:
            return
        await message.reply_text(
            "Используйте меню ниже чтобы управлять аккаунтами и уведомлениями.",
            reply_markup=self.main_menu_keyboard(),
        )

    async def add_account_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        await update.message.reply_text("Введите название аккаунта:", reply_markup=ReplyKeyboardRemove())
        return ADD_TITLE

    async def add_account_title(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        context.user_data["new_account"] = {"title": update.message.text.strip()}
        await update.message.reply_text("Введите домен магазина (например, shop.myinsales.ru):")
        return ADD_DOMAIN

    async def add_account_domain(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        context.user_data["new_account"]["shop_domain"] = update.message.text.strip()
        await update.message.reply_text("Введите API ключ:")
        return ADD_API_KEY

    async def add_account_api_key(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        context.user_data["new_account"]["api_key"] = update.message.text.strip()
        await update.message.reply_text("Введите пароль API:")
        return ADD_API_PASSWORD

    async def add_account_api_password(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        new_account = context.user_data.get("new_account", {})
        new_account["api_password"] = update.message.text.strip()

        async with SessionLocal() as session:
            account_repo = AccountRepository(session)
            try:
                info = await self._insales_client.fetch_account(
                    domain=new_account["shop_domain"],
                    api_key=new_account["api_key"],
                    password=new_account["api_password"],
                )
            except Exception:  # pylint: disable=broad-except
                await update.message.reply_text(
                    "Не удалось получить данные аккаунта. Проверьте реквизиты и попробуйте снова.",
                    reply_markup=self.main_menu_keyboard(),
                )
                return ConversationHandler.END

            try:
                await account_repo.add_account(
                    title=new_account["title"],
                    shop_domain=new_account["shop_domain"],
                    api_key=new_account["api_key"],
                    api_password=new_account["api_password"],
                    paid_till=info.paid_till,
                )
            except IntegrityError:
                await session.rollback()
                await update.message.reply_text(
                    "Аккаунт с таким доменом уже добавлен.",
                    reply_markup=self.main_menu_keyboard(),
                )
                return ConversationHandler.END

        await update.message.reply_text(
            "Аккаунт сохранён и готов к отслеживанию!",
            reply_markup=self.main_menu_keyboard(),
        )
        return ConversationHandler.END

    async def show_accounts(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        async with SessionLocal() as session:
            repo = AccountRepository(session)
            accounts = await repo.list_accounts()
        if not accounts:
            await update.message.reply_text("Аккаунты пока не добавлены.")
            return
        lines = ["Список подключённых аккаунтов:"]
        for account in accounts:
            status = "🔔" if account.notifications_enabled else "🔕"
            lines.append(f"{status} {account.title} — {account.shop_domain}")
        await update.message.reply_text("\n".join(lines))

    async def show_payment_dates(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        async with SessionLocal() as session:
            repo = AccountRepository(session)
            accounts = await repo.list_accounts()
        if not accounts:
            await update.message.reply_text("Нет данных об аккаунтах.")
            return
        lines = ["Даты оплаты:"]
        for account in accounts:
            if account.paid_till:
                lines.append(f"{account.title}: оплачено до {account.paid_till:%d.%m.%Y}")
            else:
                lines.append(f"{account.title}: дата оплаты неизвестна")
        await update.message.reply_text("\n".join(lines))

    async def toggle_notifications_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        async with SessionLocal() as session:
            repo = AccountRepository(session)
            accounts = await repo.list_accounts()
        if not accounts:
            await update.message.reply_text("Аккаунты не найдены.")
            return
        keyboard = [
            [InlineKeyboardButton(f"{account.title}", callback_data=f"toggle:{account.id}")]
            for account in accounts
        ]
        await update.message.reply_text(
            "Выберите аккаунт для изменения статуса уведомлений:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def handle_toggle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        _, account_id_str = query.data.split(":", 1)
        account_id = int(account_id_str)

        async with SessionLocal() as session:
            repo = AccountRepository(session)
            account = await repo.get_account(account_id)
            if not account:
                await query.edit_message_text("Аккаунт не найден.")
                return
            new_state = not account.notifications_enabled
            await repo.set_notification_state(account, new_state)

        status = "включены" if new_state else "выключены"
        await query.edit_message_text(f"Уведомления для {account.title} теперь {status}.")

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        await update.message.reply_text("Действие отменено.", reply_markup=self.main_menu_keyboard())
        return ConversationHandler.END

    async def _register_chat(self, update: Update) -> None:
        chat = update.effective_chat
        if not chat:
            return
        async with SessionLocal() as session:
            repo = ChatRepository(session)
            await repo.upsert_chat(
                chat_id=str(chat.id),
                username=chat.username,
                first_name=chat.first_name,
                last_name=chat.last_name,
            )

    @staticmethod
    def main_menu_keyboard() -> ReplyKeyboardMarkup:
        keyboard = [
            [MENU_LIST_ACCOUNTS, MENU_PAYMENT_DATES],
            [MENU_ADD_ACCOUNT, MENU_TOGGLE_NOTIFICATIONS],
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
