from __future__ import annotations

from typing import List
from telegram import ReplyKeyboardMarkup
from telegram.ext import ContextTypes

from ..constants import Role
from ..logging_config import logger


def build_main_keyboard(menu_items: List[tuple[str, str]], show_admin: bool) -> ReplyKeyboardMarkup:
    buttons = [[title] for _, title in menu_items]
    if show_admin:
        buttons.append(["⚙️ Админка"])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=False)


async def send_main_menu(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str = "Главное меню"):
    node_service = context.application.bot_data["node_service"]
    role_service = context.application.bot_data["role_service"]

    # Базовый пользовательский функционал (стабильные кнопки)
    base_items: List[tuple[str, str]] = [
        ("events", "📋 Мероприятия"),
        ("my_regs", "🗓 Мои регистрации"),
        ("profile", "👤 Профиль"),
    ]

    # Доп. контентные разделы (nodes) можно добавлять админом
    menu_nodes = await node_service.get_main_menu_nodes()
    node_items = [(n.key or str(n.id), n.title) for n in menu_nodes]

    role = await role_service.get_role(chat_id)
    keyboard = build_main_keyboard(
        menu_items=base_items + node_items,
        show_admin=role in (Role.ADMIN, Role.MODERATOR),
    )
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
    logger and logger.debug("Sent main menu to %s", chat_id)

