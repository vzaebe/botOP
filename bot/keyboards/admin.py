from telegram import InlineKeyboardMarkup, InlineKeyboardButton


def admin_panel_kb():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
            [InlineKeyboardButton("📤 Экспорт регистраций", callback_data="admin_export_regs")],
            [InlineKeyboardButton("👥 Экспорт пользователей", callback_data="admin_export_users")],
            [InlineKeyboardButton("➕ Добавить мероприятие", callback_data="admin_add_event")],
            [InlineKeyboardButton("✏️ Редактировать мероприятие", callback_data="admin_edit_event")],
            [InlineKeyboardButton("🗑 Удалить мероприятие", callback_data="admin_delete_event")],
            [InlineKeyboardButton("🔔 Напомнить неподтв.", callback_data="admin_remind")],
            [InlineKeyboardButton("📩 Рассылка всем", callback_data="admin_broadcast_all")],
            [InlineKeyboardButton("🎯 Рассылка по меропр.", callback_data="admin_broadcast_event")],
            [InlineKeyboardButton("🧭 Управление контентом/меню", callback_data="admin_cms")],
            [InlineKeyboardButton("👤 Роли", callback_data="admin_roles")],
            [InlineKeyboardButton("🔁 Перезагрузить данные", callback_data="admin_reload")],
            [InlineKeyboardButton("🔄 Перезапуск", callback_data="admin_restart")],
        ]
    )


def confirm_keyboard(ok_cb: str, cancel_cb: str):
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Да", callback_data=ok_cb)],
            [InlineKeyboardButton("❌ Отмена", callback_data=cancel_cb)],
        ]
    )


def cancel_keyboard(cb: str = "adm_node_cancel", text: str = "❌ Отмена") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(text, callback_data=cb)]])

