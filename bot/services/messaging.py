from __future__ import annotations

from typing import List

from telegram import ReplyKeyboardMarkup
from telegram.ext import ContextTypes

from ..constants import Role
from ..logging_config import logger

MENU_LABEL_EVENTS = "📅 Мероприятия"
MENU_LABEL_MY_REGS = "📝 Мои записи"
MENU_LABEL_PROFILE = "👤 Профиль"
ADMIN_BUTTON_TEXT = "⚙️ Админка"
DEFAULT_MENU_TEXT = "Главное меню"

BASE_MENU_ITEMS: List[tuple[str, str]] = [
    ("events", MENU_LABEL_EVENTS),
    ("my_regs", MENU_LABEL_MY_REGS),
    ("profile", MENU_LABEL_PROFILE),
]


def build_main_keyboard(menu_items: List[tuple[str, str]], show_admin: bool) -> ReplyKeyboardMarkup:
    buttons = [[title] for _, title in menu_items]
    if show_admin:
        buttons.append([ADMIN_BUTTON_TEXT])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=False)


async def send_main_menu(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str = DEFAULT_MENU_TEXT):
    node_service = context.application.bot_data["node_service"]
    role_service = context.application.bot_data["role_service"]

    menu_nodes = await node_service.get_main_menu_nodes()
    node_items = [(n.key or str(n.id), n.title) for n in menu_nodes]

    role = await role_service.get_role(chat_id)
    keyboard = build_main_keyboard(
        menu_items=BASE_MENU_ITEMS + node_items,
        show_admin=role in (Role.ADMIN, Role.MODERATOR),
    )
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
    logger and logger.debug("Sent main menu to chat_id=%s role=%s", chat_id, role)
