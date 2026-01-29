from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from ..services.messaging import MENU_LABEL_EVENTS, MENU_LABEL_MY_REGS, MENU_LABEL_PROFILE, send_main_menu
from . import content as content_handlers
from . import events as events_handlers
from . import profile as profile_handlers

logger = logging.getLogger(__name__)


async def main_menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия по основным кнопкам меню."""
    text = (update.message.text or "").strip()

    if text == MENU_LABEL_EVENTS:
        return await events_handlers.list_events(update, context)
    if text == MENU_LABEL_MY_REGS:
        return await events_handlers.list_my_registrations(update, context)
    if text == MENU_LABEL_PROFILE:
        return await profile_handlers.show_profile(update, context)

    node_service = context.application.bot_data.get("node_service")
    if node_service:
        cache = context.application.bot_data.get("main_menu_cache")
        if cache is None:
            nodes = await node_service.get_main_menu_nodes()
            cache = {n.title: n for n in nodes}
            context.application.bot_data["main_menu_cache"] = cache
        node = cache.get(text)
        if node:
            return await content_handlers.show_node(update, context, node, is_callback=False)

    await send_main_menu(context, update.effective_chat.id, text="Не понял запрос, держите меню:")
    logger.debug("Unknown menu action text=%r chat_id=%s", text, update.effective_chat.id)


def setup_handlers(application):
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu_router))
