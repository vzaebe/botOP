from __future__ import annotations

import asyncio
import io
from datetime import datetime
from typing import Optional

import pandas as pd
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from ..constants import Conversation, Role
from ..keyboards.admin import admin_panel_kb, confirm_keyboard
from ..services.permissions import require_role
from ..utils.errors import ValidationError
from ..utils.validators import parse_int
from ..logging_config import logger


def _event_list_keyboard(events, prefix: str):
    rows = []
    for ev in events:
        rows.append([InlineKeyboardButton(ev.name, callback_data=f"{prefix}_{ev.event_id}")])
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="admin_panel")])
    return InlineKeyboardMarkup(rows)


@require_role(Role.MODERATOR)
async def admin_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Админ-панель", reply_markup=admin_panel_kb())


async def admin_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введите админ-пароль:")
    return Conversation.WAITING_ADMIN_PASSWORD


async def admin_login_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = context.application.bot_data["config"]
    if update.message.text.strip() != cfg.admin_password:
        await update.message.reply_text("❌ Неверный пароль.")
        return ConversationHandler.END
    profile_service = context.application.bot_data["profile_service"]
    await profile_service.assign_role(update.effective_user.id, Role.ADMIN)
    await update.message.reply_text("✅ Роль admin выдана.", reply_markup=admin_panel_kb())
    return ConversationHandler.END


@require_role(Role.MODERATOR)
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Админ-панель", reply_markup=admin_panel_kb())


@require_role(Role.MODERATOR)
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    event_service = context.application.bot_data["event_service"]
    events = await event_service.list_active_events()
    lines = []
    total_reg = total_confirm = 0
    for ev in events:
        regs = await event_service.list_registrations(ev.event_id)
        confirmed = len([r for r in regs if r.status == "confirmed"])
        total_reg += len(regs)
        total_confirm += confirmed
        lines.append(f"{ev.name}: {len(regs)} (✅ {confirmed}, ❌ {len(regs)-confirmed})")
    text = "Статистика:\n" + "\n".join(lines) if lines else "Нет мероприятий"
    text += f"\n\nВсего: {total_reg}, подтвердили: {total_confirm}"
    await query.edit_message_text(text, reply_markup=admin_panel_kb())


@require_role(Role.MODERATOR)
async def export_regs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_repo = context.application.bot_data["profile_service"].user_repo
    event_service = context.application.bot_data["event_service"]
    data = []
    events = await event_service.event_repo.list_events()
    for ev in events:
        regs = await event_service.list_registrations(ev.event_id)
        for reg in regs:
            user = await user_repo.get_user(reg.user_id)
            data.append(
                {
                    "event_id": ev.event_id,
                    "event_name": ev.name,
                    "user_id": reg.user_id,
                    "full_name": user.full_name if user else "",
                    "email": user.email if user else "",
                    "status": reg.status,
                    "reg_time": reg.reg_time,
                }
            )
    df = pd.DataFrame(data)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="registrations")
    buffer.seek(0)
    await context.bot.send_document(
        chat_id=query.message.chat_id,
        document=buffer,
        filename="registrations.xlsx",
        caption="Экспорт регистраций",
    )
    await query.edit_message_text("Готово", reply_markup=admin_panel_kb())


@require_role(Role.MODERATOR)
async def export_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    profile_service = context.application.bot_data["profile_service"]
    users = await profile_service.list_users()
    df = pd.DataFrame(
        [
            {
                "user_id": u.user_id,
                "username": u.username,
                "full_name": u.full_name,
                "email": u.email,
                "consent": u.consent,
                "consent_time": u.consent_time,
            }
            for u in users
        ]
    )
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="users")
    buffer.seek(0)
    await context.bot.send_document(
        chat_id=query.message.chat_id,
        document=buffer,
        filename="users.xlsx",
        caption="Экспорт пользователей",
    )
    await query.edit_message_text("Экспорт отправлен", reply_markup=admin_panel_kb())


@require_role(Role.MODERATOR)
async def add_event_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Введите название мероприятия:")
    return Conversation.WAITING_EVENT_NAME


async def add_event_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_event_name"] = update.message.text.strip()
    await update.message.reply_text("Введите дату и время (YYYY-MM-DD HH:MM):")
    return Conversation.WAITING_EVENT_DATETIME


async def add_event_datetime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_event_dt"] = update.message.text.strip()
    await update.message.reply_text("Введите описание:")
    return Conversation.WAITING_EVENT_DESC


async def add_event_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_event_desc"] = update.message.text.strip()
    await update.message.reply_text("Введите число мест:")
    return Conversation.WAITING_EVENT_SEATS


async def add_event_seats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    seats = parse_int(update.message.text.strip())
    if not seats or seats <= 0:
        await update.message.reply_text("Введите положительное число мест:")
        return Conversation.WAITING_EVENT_SEATS
    event_service = context.application.bot_data["event_service"]
    try:
        ev = await event_service.add_event(
            context.user_data["new_event_name"],
            context.user_data["new_event_dt"],
            context.user_data["new_event_desc"],
            seats,
        )
    except ValidationError as exc:
        await update.message.reply_text(f"❌ {exc}")
        return Conversation.WAITING_EVENT_NAME
    await update.message.reply_text(f"✅ Добавлено: {ev.name}")
    await update.message.reply_text("Админ-панель", reply_markup=admin_panel_kb())
    return ConversationHandler.END


@require_role(Role.MODERATOR)
async def edit_event_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    events = await context.application.bot_data["event_service"].event_repo.list_events()
    if not events:
        await query.edit_message_text("Нет мероприятий", reply_markup=admin_panel_kb())
        return ConversationHandler.END
    await query.edit_message_text("Выберите мероприятие:", reply_markup=_event_list_keyboard(events, "admin_edit_pick"))
    return ConversationHandler.END


@require_role(Role.MODERATOR)
async def edit_event_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    event_id = query.data.replace("admin_edit_pick_", "")
    context.user_data["edit_event_id"] = event_id
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Название", callback_data="admin_edit_field_name")],
            [InlineKeyboardButton("Дата/время", callback_data="admin_edit_field_datetime_str")],
            [InlineKeyboardButton("Описание", callback_data="admin_edit_field_description")],
            [InlineKeyboardButton("Места", callback_data="admin_edit_field_max_seats")],
        ]
    )
    await query.edit_message_text("Что изменить?", reply_markup=kb)


@require_role(Role.MODERATOR)
async def edit_event_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    field = query.data.replace("admin_edit_field_", "")
    context.user_data["edit_field"] = field
    await query.edit_message_text("Введите новое значение:")
    return Conversation.EDIT_EVENT_VALUE


async def edit_event_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    event_service = context.application.bot_data["event_service"]
    event_id = context.user_data.get("edit_event_id")
    field = context.user_data.get("edit_field")
    try:
        await event_service.update_event_field(event_id, field, update.message.text.strip())
    except ValidationError as exc:
        await update.message.reply_text(f"❌ {exc}")
        return Conversation.EDIT_EVENT_VALUE
    await update.message.reply_text("Обновлено", reply_markup=admin_panel_kb())
    return ConversationHandler.END


@require_role(Role.MODERATOR)
async def delete_event_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    events = await context.application.bot_data["event_service"].event_repo.list_events()
    if not events:
        await query.edit_message_text("Нет мероприятий", reply_markup=admin_panel_kb())
        return
    await query.edit_message_text("Удалить какое?", reply_markup=_event_list_keyboard(events, "admin_delete_pick"))


@require_role(Role.MODERATOR)
async def delete_event_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    event_id = query.data.replace("admin_delete_pick_", "")
    await query.edit_message_text(
        f"Удалить {event_id}?", reply_markup=confirm_keyboard(f"admin_delete_go_{event_id}", "admin_panel")
    )


@require_role(Role.MODERATOR)
async def delete_event_go(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    event_id = query.data.replace("admin_delete_go_", "")
    await context.application.bot_data["event_service"].delete_event(event_id)
    await query.edit_message_text("Удалено", reply_markup=admin_panel_kb())


@require_role(Role.MODERATOR)
async def remind_unconfirmed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    events = await context.application.bot_data["event_service"].event_repo.list_events()
    await query.edit_message_text("Выберите мероприятие:", reply_markup=_event_list_keyboard(events, "admin_remind_pick"))


@require_role(Role.MODERATOR)
async def remind_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    event_id = query.data.replace("admin_remind_pick_", "")
    event_service = context.application.bot_data["event_service"]
    regs = await event_service.list_registrations(event_id)
    target = [r for r in regs if r.status != "confirmed"]
    sent = 0
    for reg in target:
        try:
            await context.bot.send_message(
                chat_id=reg.user_id,
                text="⏰ Пожалуйста, подтвердите участие в мероприятии.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("✅ Подтвердить", callback_data=f"event_confirm_{event_id}")]]
                ),
            )
            sent += 1
            await asyncio.sleep(0.05)
        except Exception as exc:  # noqa: BLE001
            logger and logger.warning("Reminder failed for %s: %s", reg.user_id, exc)
    await query.edit_message_text(f"Напоминания отправлены: {sent}", reply_markup=admin_panel_kb())


@require_role(Role.MODERATOR)
async def broadcast_all_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Введите текст рассылки:")
    return Conversation.WAITING_BROADCAST_MESSAGE


async def broadcast_all_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    context.user_data["broadcast_text"] = text
    kb = confirm_keyboard("admin_broadcast_send", "admin_panel")
    await update.message.reply_text(f"Отправить сообщение всем ({len(await context.application.bot_data['profile_service'].list_users())})?", reply_markup=kb)
    return Conversation.WAITING_BROADCAST_CONFIRM


@require_role(Role.MODERATOR)
async def broadcast_all_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = context.user_data.get("broadcast_text", "")
    users = await context.application.bot_data["profile_service"].list_users()
    sent = 0
    for u in users:
        try:
            await context.bot.send_message(chat_id=u.user_id, text=text)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception as exc:  # noqa: BLE001
            logger and logger.warning("Broadcast fail %s: %s", u.user_id, exc)
    await query.edit_message_text(f"Рассылка завершена. Доставлено: {sent}", reply_markup=admin_panel_kb())
    return ConversationHandler.END


@require_role(Role.MODERATOR)
async def broadcast_event_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    events = await context.application.bot_data["event_service"].event_repo.list_events()
    await query.edit_message_text("Выберите мероприятие для рассылки:", reply_markup=_event_list_keyboard(events, "admin_broadcast_pick"))


@require_role(Role.MODERATOR)
async def broadcast_event_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    event_id = query.data.replace("admin_broadcast_pick_", "")
    context.user_data["broadcast_event_id"] = event_id
    await query.edit_message_text("Введите текст рассылки по мероприятию:")
    return Conversation.WAITING_EVENT_BROADCAST_MESSAGE


async def broadcast_event_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["broadcast_text"] = update.message.text
    kb = confirm_keyboard("admin_broadcast_event_send", "admin_panel")
    await update.message.reply_text("Подтвердить рассылку по мероприятию?", reply_markup=kb)
    return Conversation.WAITING_EVENT_BROADCAST_CONFIRM


@require_role(Role.MODERATOR)
async def broadcast_event_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = context.user_data.get("broadcast_text", "")
    event_id = context.user_data.get("broadcast_event_id")
    regs = await context.application.bot_data["event_service"].list_registrations(event_id)
    sent = 0
    for reg in regs:
        try:
            await context.bot.send_message(chat_id=reg.user_id, text=text)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception as exc:  # noqa: BLE001
            logger and logger.warning("Broadcast event fail %s: %s", reg.user_id, exc)
    await query.edit_message_text(f"Рассылка по событию завершена. Доставлено: {sent}", reply_markup=admin_panel_kb())
    return ConversationHandler.END


# CMS
@require_role(Role.ADMIN)
async def cms_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    content_service = context.application.bot_data["content_service"]
    sections = await content_service.list_sections()
    rows = [[InlineKeyboardButton(s.title, callback_data=f"cms_view_{s.key}")] for s in sections]
    rows.append([InlineKeyboardButton("➕ Добавить", callback_data="cms_add")])
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="admin_panel")])
    await query.edit_message_text("Контентные разделы:", reply_markup=InlineKeyboardMarkup(rows))


@require_role(Role.ADMIN)
async def cms_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    key = query.data.replace("cms_view_", "")
    content_service = context.application.bot_data["content_service"]
    section = await content_service.get_section(key)
    if not section:
        await query.edit_message_text("Раздел не найден", reply_markup=admin_panel_kb())
        return
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✏️ Редактировать", callback_data=f"cms_edit_{key}")],
            [InlineKeyboardButton("🗑 Удалить", callback_data=f"cms_del_{key}")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="admin_panel")],
        ]
    )
    await query.edit_message_text(f"{section.title}\n\n{section.body}", reply_markup=kb)


@require_role(Role.ADMIN)
async def cms_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Введите ключ раздела (латиница/цифры):")
    return Conversation.EDIT_CONTENT_KEY


async def cms_add_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["cms_key"] = update.message.text.strip()
    await update.message.reply_text("Введите заголовок:")
    return Conversation.EDIT_CONTENT_TITLE


async def cms_add_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["cms_title"] = update.message.text.strip()
    await update.message.reply_text("Введите текст:")
    return Conversation.EDIT_CONTENT_BODY


async def cms_add_body(update: Update, context: ContextTypes.DEFAULT_TYPE):
    content_service = context.application.bot_data["content_service"]
    await content_service.save_section(
        context.user_data["cms_key"], context.user_data["cms_title"], update.message.text
    )
    await update.message.reply_text("Сохранено", reply_markup=admin_panel_kb())
    return ConversationHandler.END


@require_role(Role.ADMIN)
async def cms_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    key = query.data.replace("cms_del_", "")
    await context.application.bot_data["content_service"].delete_section(key)
    await query.edit_message_text("Удалено", reply_markup=admin_panel_kb())


# Menu management
@require_role(Role.ADMIN)
async def menu_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    content_service = context.application.bot_data["content_service"]
    items = await content_service.list_menu_items()
    rows = [[InlineKeyboardButton(i.title, callback_data=f"menu_edit_{i.key}")] for i in items]
    rows.append([InlineKeyboardButton("➕ Добавить", callback_data="menu_add")])
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="admin_panel")])
    await query.edit_message_text("Главное меню:", reply_markup=InlineKeyboardMarkup(rows))


@require_role(Role.ADMIN)
async def menu_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Введите ключ|текст|позиция (через |):")
    return Conversation.EDIT_MENU_ITEM


async def menu_add_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    content_service = context.application.bot_data["content_service"]
    try:
        key, title, pos = [x.strip() for x in update.message.text.split("|", 2)]
        position = int(pos)
        await content_service.save_menu_item(key, title, position)
        await update.message.reply_text("Меню обновлено", reply_markup=admin_panel_kb())
    except Exception:
        await update.message.reply_text("Формат: key|Текст|позиция")
        return Conversation.EDIT_MENU_ITEM
    return ConversationHandler.END


# Roles
@require_role(Role.ADMIN)
async def roles_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    profile_service = context.application.bot_data["profile_service"]
    users = await profile_service.list_users()
    rows = [
        [InlineKeyboardButton(f"{u.full_name or u.username} ({u.user_id})", callback_data=f"role_pick_{u.user_id}")]
        for u in users
    ]
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="admin_panel")])
    await query.edit_message_text("Выберите пользователя для назначения роли:", reply_markup=InlineKeyboardMarkup(rows))


@require_role(Role.ADMIN)
async def role_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = int(query.data.replace("role_pick_", ""))
    context.user_data["role_user_id"] = uid
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("admin", callback_data="role_set_admin")],
            [InlineKeyboardButton("moderator", callback_data="role_set_moderator")],
            [InlineKeyboardButton("user", callback_data="role_set_user")],
        ]
    )
    await query.edit_message_text("Выберите роль:", reply_markup=kb)


@require_role(Role.ADMIN)
async def role_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    role_name = query.data.replace("role_set_", "")
    uid = context.user_data.get("role_user_id")
    profile_service = context.application.bot_data["profile_service"]
    await profile_service.assign_role(uid, Role(role_name))
    await query.edit_message_text("Роль обновлена", reply_markup=admin_panel_kb())


@require_role(Role.ADMIN)
async def reload_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    restart_service = context.application.bot_data["restart_service"]
    await restart_service.reload_data(context)
    await query.edit_message_text("Данные перечитаны", reply_markup=admin_panel_kb())


@require_role(Role.ADMIN)
async def restart_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    restart_service = context.application.bot_data["restart_service"]
    await restart_service.schedule_restart(update, context, code=0)


def setup_handlers(application):
    conv = ConversationHandler(
        entry_points=[],
        states={
            Conversation.WAITING_ADMIN_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_login_check)],
            Conversation.WAITING_EVENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_event_name)],
            Conversation.WAITING_EVENT_DATETIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_event_datetime)],
            Conversation.WAITING_EVENT_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_event_desc)],
            Conversation.WAITING_EVENT_SEATS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_event_seats)],
            Conversation.EDIT_EVENT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_event_value)],
            Conversation.WAITING_BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_all_message)],
            Conversation.WAITING_BROADCAST_CONFIRM: [CallbackQueryHandler(broadcast_all_send, pattern="^admin_broadcast_send$")],
            Conversation.WAITING_EVENT_BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_event_text)],
            Conversation.WAITING_EVENT_BROADCAST_CONFIRM: [CallbackQueryHandler(broadcast_event_send, pattern="^admin_broadcast_event_send$")],
            Conversation.EDIT_CONTENT_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, cms_add_key)],
            Conversation.EDIT_CONTENT_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, cms_add_title)],
            Conversation.EDIT_CONTENT_BODY: [MessageHandler(filters.TEXT & ~filters.COMMAND, cms_add_body)],
            Conversation.EDIT_MENU_ITEM: [MessageHandler(filters.TEXT & ~filters.COMMAND, menu_add_value)],
        },
        fallbacks=[],
        per_user=True,
    )
    application.add_handler(conv)
    application.add_handler(MessageHandler(filters.Command("admin"), admin_login))
    application.add_handler(MessageHandler(filters.Regex("^⚙️ Админка$"), admin_entry))
    application.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    application.add_handler(CallbackQueryHandler(stats, pattern="^admin_stats$"))
    application.add_handler(CallbackQueryHandler(export_regs, pattern="^admin_export_regs$"))
    application.add_handler(CallbackQueryHandler(export_users, pattern="^admin_export_users$"))
    application.add_handler(CallbackQueryHandler(add_event_start, pattern="^admin_add_event$"))
    application.add_handler(CallbackQueryHandler(edit_event_start, pattern="^admin_edit_event$"))
    application.add_handler(CallbackQueryHandler(edit_event_pick, pattern="^admin_edit_pick_.*$"))
    application.add_handler(CallbackQueryHandler(edit_event_field, pattern="^admin_edit_field_.*$"))
    application.add_handler(CallbackQueryHandler(delete_event_start, pattern="^admin_delete_event$"))
    application.add_handler(CallbackQueryHandler(delete_event_confirm, pattern="^admin_delete_pick_.*$"))
    application.add_handler(CallbackQueryHandler(delete_event_go, pattern="^admin_delete_go_.*$"))
    application.add_handler(CallbackQueryHandler(remind_unconfirmed, pattern="^admin_remind$"))
    application.add_handler(CallbackQueryHandler(remind_send, pattern="^admin_remind_pick_.*$"))
    application.add_handler(CallbackQueryHandler(broadcast_all_start, pattern="^admin_broadcast_all$"))
    application.add_handler(CallbackQueryHandler(broadcast_event_start, pattern="^admin_broadcast_event$"))
    application.add_handler(CallbackQueryHandler(broadcast_event_pick, pattern="^admin_broadcast_pick_.*$"))
    application.add_handler(CallbackQueryHandler(cms_start, pattern="^admin_cms$"))
    application.add_handler(CallbackQueryHandler(cms_view, pattern="^cms_view_.*$"))
    application.add_handler(CallbackQueryHandler(cms_add, pattern="^cms_add$"))
    application.add_handler(CallbackQueryHandler(cms_delete, pattern="^cms_del_.*$"))
    application.add_handler(CallbackQueryHandler(menu_start, pattern="^admin_menu$"))
    application.add_handler(CallbackQueryHandler(menu_add, pattern="^menu_add$"))
    application.add_handler(CallbackQueryHandler(roles_start, pattern="^admin_roles$"))
    application.add_handler(CallbackQueryHandler(role_pick, pattern="^role_pick_.*$"))
    application.add_handler(CallbackQueryHandler(role_set, pattern="^role_set_.*$"))
    application.add_handler(CallbackQueryHandler(reload_data, pattern="^admin_reload$"))
    application.add_handler(CallbackQueryHandler(restart_bot, pattern="^admin_restart$"))

