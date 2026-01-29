from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from ..constants import Conversation
from ..services.messaging import send_main_menu

logger = logging.getLogger(__name__)


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
                [InlineKeyboardButton("✅ Да, согласен", callback_data="consent_accept")],
                [InlineKeyboardButton("❌ Нет, отказаться", callback_data="consent_decline")],
            ]
        )
        await update.message.reply_text(
            (
                "Мне нужно ваше согласие на обработку персональных данных, "
                "чтобы сохранить профиль и записи. Политика: "
                f"{config.personal_data_link}"
            ),
            reply_markup=kb,
        )
        logger.info("Asked for consent user_id=%s", user.id)
        return Conversation.CONFIRM_PROFILE

    await send_main_menu(context, chat_id=user.id, text="Готово, что делаем дальше?")
    logger.debug("User %s already consented; showing menu", user.id)


async def consent_accept(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    profile_service = context.application.bot_data["profile_service"]
    await profile_service.set_consent(query.from_user.id, True)
    await query.edit_message_text("✅ Согласие учтено. Добро пожаловать!")
    await send_main_menu(context, chat_id=query.from_user.id, text="Главное меню")
    logger.info("Consent accepted user_id=%s", query.from_user.id)


async def consent_decline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Ок, без согласия бот не сможет работать. Если передумаете — нажмите /start."
    )
    logger.info("Consent declined user_id=%s", query.from_user.id)


def setup_handlers(application):
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(consent_accept, pattern="^consent_accept$"))
    application.add_handler(CallbackQueryHandler(consent_decline, pattern="^consent_decline$"))
