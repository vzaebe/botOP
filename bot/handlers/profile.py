from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from ..constants import Conversation
from ..services.messaging import send_main_menu
from ..utils.errors import ValidationError

logger = logging.getLogger(__name__)


async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile_service = context.application.bot_data["profile_service"]
    role_service = context.application.bot_data["role_service"]
    user = await profile_service.get_profile(update.effective_user.id)
    if not user or not user.consent:
        await update.message.reply_text(
            "Нужно согласие на обработку данных. Нажмите /start, чтобы продолжить."
        )
        return ConversationHandler.END

    role = await role_service.get_role(update.effective_user.id)
    text = (
        "👤 Профиль\n"
        f"Имя: {user.full_name or '—'}\n"
        f"Email: {user.email or '—'}\n"
        f"Роль: {role.value}\n"
        f"Согласие на обработку: {'Да' if user.consent else 'Нет'}"
    )
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✏️ Изменить имя", callback_data="profile_edit_name")],
            [InlineKeyboardButton("✉️ Изменить email", callback_data="profile_edit_email")],
            [InlineKeyboardButton("↩️ В меню", callback_data="profile_back")],
        ]
    )
    await update.message.reply_text(text, reply_markup=kb)
    return ConversationHandler.END


async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Введите ваше имя и фамилию:")
    return Conversation.INPUT_NAME


async def ask_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Введите ваш email:")
    return Conversation.INPUT_EMAIL


async def save_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile_service = context.application.bot_data["profile_service"]
    try:
        await profile_service.update_full_name(update.effective_user.id, update.message.text)
        await update.message.reply_text("✅ Имя обновлено.")
        logger.info("Updated name for user_id=%s", update.effective_user.id)
    except ValidationError as exc:
        await update.message.reply_text(f"⚠️ {exc}")
        return Conversation.INPUT_NAME
    await send_main_menu(context, update.effective_chat.id, text="Профиль обновлен. Что дальше?")
    return ConversationHandler.END


async def save_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile_service = context.application.bot_data["profile_service"]
    try:
        await profile_service.update_email(update.effective_user.id, update.message.text)
        await update.message.reply_text("✅ Email обновлен.")
        logger.info("Updated email for user_id=%s", update.effective_user.id)
    except ValidationError as exc:
        await update.message.reply_text(f"⚠️ {exc}")
        return Conversation.INPUT_EMAIL
    await send_main_menu(context, update.effective_chat.id, text="Профиль обновлен. Что дальше?")
    return ConversationHandler.END


async def back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await send_main_menu(context, query.from_user.id)
    return ConversationHandler.END


def setup_handlers(application):
    conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(ask_name, pattern="^profile_edit_name$"),
            CallbackQueryHandler(ask_email, pattern="^profile_edit_email$"),
        ],
        states={
            Conversation.INPUT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_name)],
            Conversation.INPUT_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_email)],
        },
        fallbacks=[],
        per_user=True,
    )
    application.add_handler(conv)
    application.add_handler(CallbackQueryHandler(back, pattern="^profile_back$"))
    application.add_handler(MessageHandler(filters.Regex("^👤 Профиль$"), show_profile))
