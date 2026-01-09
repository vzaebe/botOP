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
    content_service = context.application.bot_data["content_service"]
    role_service = context.application.bot_data["role_service"]
    menu_items = await content_service.list_menu_items()
    role = await role_service.get_role(chat_id)
    keyboard = build_main_keyboard(
        menu_items=[(m.key, m.title) for m in menu_items],
        show_admin=role in (Role.ADMIN, Role.MODERATOR),
    )
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
    logger and logger.debug("Sent main menu to %s", chat_id)

