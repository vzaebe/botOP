from __future__ import annotations

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)

from ..constants import Conversation
from ..services.messaging import send_main_menu
from ..utils.errors import ValidationError


async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile_service = context.application.bot_data["profile_service"]
    user = await profile_service.get_profile(update.effective_user.id)
    if not user or not user.consent:
        await update.message.reply_text("Необходимо согласие на обработку ПДн. Нажмите /start.")
        return ConversationHandler.END

    text = (
        f"👤 Профиль\n"
        f"Имя: {user.full_name or '—'}\n"
        f"Email: {user.email or '—'}\n"
        f"Согласие ПДн: {'✅' if user.consent else '❌'}"
    )
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✏️ Изменить ФИО", callback_data="profile_edit_name")],
            [InlineKeyboardButton("✏️ Изменить email", callback_data="profile_edit_email")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="profile_back")],
        ]
    )
    await update.message.reply_text(text, reply_markup=kb)
    return ConversationHandler.END


async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Введите новое ФИО:")
    return Conversation.INPUT_NAME


async def ask_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Введите новый email:")
    return Conversation.INPUT_EMAIL


async def save_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile_service = context.application.bot_data["profile_service"]
    try:
        await profile_service.update_full_name(update.effective_user.id, update.message.text)
        await update.message.reply_text("✅ Имя обновлено.")
    except ValidationError as exc:
        await update.message.reply_text(f"❌ {exc}")
        return Conversation.INPUT_NAME
    await send_main_menu(context, update.effective_chat.id)
    return ConversationHandler.END


async def save_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile_service = context.application.bot_data["profile_service"]
    try:
        await profile_service.update_email(update.effective_user.id, update.message.text)
        await update.message.reply_text("✅ Email обновлён.")
    except ValidationError as exc:
        await update.message.reply_text(f"❌ {exc}")
        return Conversation.INPUT_EMAIL
    await send_main_menu(context, update.effective_chat.id)
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

