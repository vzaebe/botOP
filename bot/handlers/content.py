from __future__ import annotations

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters


async def info_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    content_service = context.application.bot_data["content_service"]
    sections = await content_service.list_sections()
    rows = [[InlineKeyboardButton(s.title, callback_data=f"info_{s.key}")] for s in sections]
    if not rows:
        await update.message.reply_text("Нет доступных разделов.")
        return
    await update.message.reply_text("Информация:", reply_markup=InlineKeyboardMarkup(rows))


async def info_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    key = query.data.replace("info_", "")
    section = await context.application.bot_data["content_service"].get_section(key)
    if not section:
        await query.edit_message_text("Раздел не найден.")
        return
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="admin_panel")]])
    await query.edit_message_text(f"{section.title}\n\n{section.body}", reply_markup=kb, parse_mode="Markdown")


def setup_handlers(application):
    application.add_handler(MessageHandler(filters.Regex("^ℹ️ Инфо$"), info_menu))
    application.add_handler(CallbackQueryHandler(info_view, pattern="^info_.*$"))

