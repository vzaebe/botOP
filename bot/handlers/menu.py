from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from ..services.messaging import send_main_menu
from . import events as events_handlers
from . import profile as profile_handlers
from . import content as content_handlers


async def main_menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Единый роутер ReplyKeyboard-кнопок (и для nodes, и для базовых разделов)."""
    text = (update.message.text or "").strip()

    if text == "📋 Мероприятия":
        return await events_handlers.list_events(update, context)
    if text == "🗓 Мои регистрации":
        return await events_handlers.list_my_registrations(update, context)
    if text == "👤 Профиль":
        return await profile_handlers.show_profile(update, context)

    # Если это node-раздел из главного меню
    node_service = context.application.bot_data.get("node_service")
    if node_service:
        nodes = await node_service.get_main_menu_nodes()
        node = next((n for n in nodes if n.title == text), None)
        if node:
            return await content_handlers.show_node(update, context, node, is_callback=False)

    # Неизвестный текст — просто покажем меню ещё раз
    await send_main_menu(context, update.effective_chat.id, text="Выберите действие:")


def setup_handlers(application):
    # Должен добавляться ПОСЛЕ ConversationHandler-ов и специализированных MessageHandler-ов.
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu_router))

