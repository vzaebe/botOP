from __future__ import annotations

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from ..services.messaging import send_main_menu
from ..constants import Conversation


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    profile_service = context.application.bot_data["profile_service"]
    config = context.application.bot_data["config"]
    await profile_service.ensure_user(
        user_id=user.id, username=user.username or "", full_name=user.full_name or ""
    )

    profile = await profile_service.get_profile(user.id)
    consent = profile.consent if profile else False
    if not consent:
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("✅ Принимаю", callback_data="consent_accept")],
                [InlineKeyboardButton("❌ Не принимаю", callback_data="consent_decline")],
            ]
        )
        await update.message.reply_text(
            f"Продолжая, вы соглашаетесь с обработкой персональных данных: {config.personal_data_link}",
            reply_markup=kb,
        )
        return Conversation.CONFIRM_PROFILE

    await send_main_menu(context, chat_id=user.id, text="Добро пожаловать!")


async def consent_accept(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    profile_service = context.application.bot_data["profile_service"]
    await profile_service.set_consent(query.from_user.id, True)
    await query.edit_message_text("✅ Спасибо за согласие на обработку ПДн.")
    await send_main_menu(context, chat_id=query.from_user.id, text="Главное меню")


async def consent_decline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Без согласия на обработку ПДн использование бота ограничено.")


def setup_handlers(application):
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(consent_accept, pattern="^consent_accept$"))
    application.add_handler(CallbackQueryHandler(consent_decline, pattern="^consent_decline$"))

