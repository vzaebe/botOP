from __future__ import annotations

import logging
from urllib.parse import urlparse

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes, MessageHandler, filters

logger = logging.getLogger(__name__)


def _is_valid_http_url(value: str) -> bool:
    value = (value or "").strip()
    if not value:
        return False
    try:
        parsed = urlparse(value)
    except Exception:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


async def node_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for all dynamic node navigation."""
    query = update.callback_query
    await query.answer()

    node_id = int(query.data.replace("node_", ""))
    node_service = context.application.bot_data["node_service"]
    node = await node_service.get_node(node_id)

    if not node:
        await query.edit_message_text("Раздел не найден.")
        return

    await show_node(update, context, node, is_callback=True)


async def show_node(
    update: Update, context: ContextTypes.DEFAULT_TYPE, node, is_callback: bool
):
    node_service = context.application.bot_data["node_service"]
    children = await node_service.get_children(node.id)

    keyboard: list[list[InlineKeyboardButton]] = []
    for child in children:
        if child.url and _is_valid_http_url(child.url):
            keyboard.append([InlineKeyboardButton(child.title, url=child.url)])
        else:
            if child.url and not _is_valid_http_url(child.url):
                logger.warning("Invalid URL in node id=%s: %r", getattr(child, "id", None), child.url)
            keyboard.append([InlineKeyboardButton(child.title, callback_data=f"node_{child.id}")])

    if node.parent_id is not None:
        keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data=f"node_{node.parent_id}")])
    elif is_callback:
        keyboard.append([InlineKeyboardButton("✖️ Закрыть меню", callback_data="main_menu_close")])

    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

    if is_callback:
        await update.callback_query.edit_message_text(
            node.content, reply_markup=reply_markup, parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            node.content, reply_markup=reply_markup, parse_mode="Markdown"
        )


async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for all reply keyboard buttons that correspond to nodes."""
    text = update.message.text
    if not text:
        return None

    node_service = context.application.bot_data["node_service"]

    cache = context.application.bot_data.get("main_menu_cache")
    if cache is None:
        nodes = await node_service.get_main_menu_nodes()
        cache = {n.title: n for n in nodes}
        context.application.bot_data["main_menu_cache"] = cache

    node = cache.get(text)
    if node:
        await show_node(update, context, node, is_callback=False)
    else:
        return None


async def close_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        await query.delete_message()
    except Exception:  # noqa: BLE001
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:  # noqa: BLE001
            pass


def setup_handlers(application):
    application.add_handler(CallbackQueryHandler(close_menu, pattern="^main_menu_close$"))
    application.add_handler(CallbackQueryHandler(node_view, pattern=r"^node_\d+$"))
