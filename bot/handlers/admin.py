from __future__ import annotations

import asyncio
import io
from datetime import datetime
import sys
import time
from typing import Optional

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from ..constants import Conversation, Role
from ..keyboards.admin import admin_panel_kb, cancel_keyboard, confirm_keyboard
from ..services.messaging import ADMIN_BUTTON_TEXT
from ..services.permissions import require_role
from ..utils.errors import ValidationError
from ..utils.validators import parse_int
from ..logging_config import logger
from ..utils.admin_diagnostics import (
    format_seconds,
    read_last_lines,
    try_read_proc_loadavg,
    try_read_proc_meminfo,
)


_CMS_DRAFT_KEYS = [
    "cms_node_id",
    "cms_parent_id",
    "cms_key",
    "cms_title",
    "cms_content",
    "cms_url",
    "cms_order",
    "cms_is_main",
]


def _clear_cms_draft(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in _CMS_DRAFT_KEYS:
        context.user_data.pop(key, None)


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
    logger and logger.info("Admin access granted to user_id=%s", update.effective_user.id)
    return ConversationHandler.END


@require_role(Role.MODERATOR)
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Админ-панель", reply_markup=admin_panel_kb())


@require_role(Role.MODERATOR)
async def admin_status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = context.application.bot_data["config"]
    started_at = context.application.bot_data.get("started_at")
    uptime = format_seconds(time.time() - started_at) if started_at else "unknown"

    db = context.application.bot_data.get("db")
    users = events = regs = "n/a"
    if db:
        try:
            row = await db.fetchone("SELECT COUNT(*) AS c FROM users")
            users = str(int(row["c"])) if row else "0"
            row = await db.fetchone("SELECT COUNT(*) AS c FROM events")
            events = str(int(row["c"])) if row else "0"
            row = await db.fetchone("SELECT COUNT(*) AS c FROM registrations")
            regs = str(int(row["c"])) if row else "0"
        except Exception:
            users = events = regs = "err"

    loadavg = try_read_proc_loadavg()
    meminfo = try_read_proc_meminfo()

    lines = [
        "✅ admin_status",
        f"uptime: {uptime}",
        f"python: {sys.version.split()[0]}",
        f"db: {cfg.database_path}",
        f"log_level: {cfg.log_level}",
        f"log_file: {getattr(cfg, 'log_file', '')}",
        f"restart_enabled: {cfg.restart_enabled}",
        f"counts: users={users}, events={events}, registrations={regs}",
    ]
    if loadavg:
        lines.append(f"loadavg: {loadavg}")
    if meminfo:
        lines.append("meminfo:")
        lines.append(meminfo)

    await update.effective_message.reply_text("\n".join(lines))


@require_role(Role.MODERATOR)
async def admin_health_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.application.bot_data.get("db")
    if not db:
        await update.effective_message.reply_text("❌ DB: not configured")
        return

    checks: list[str] = []
    try:
        await db.fetchone("SELECT 1 AS ok")
        checks.append("✅ db: query_ok")
    except Exception as exc:
        checks.append(f"❌ db: query_failed ({exc.__class__.__name__})")

    try:
        row = await db.fetchone("PRAGMA foreign_keys;")
        fk = row[0] if row else None
        checks.append(f"✅ sqlite: foreign_keys={fk}")
    except Exception as exc:
        checks.append(f"⚠️ sqlite: foreign_keys check failed ({exc.__class__.__name__})")

    try:
        rows = await db.fetchall(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        have = {r["name"] for r in rows}
        expected = {"users", "roles", "events", "registrations", "content_sections", "menu_items", "templates", "nodes"}
        missing = sorted(expected - have)
        if missing:
            checks.append(f"❌ schema: missing tables: {', '.join(missing)}")
        else:
            checks.append("✅ schema: tables_ok")
    except Exception as exc:
        checks.append(f"❌ schema: check_failed ({exc.__class__.__name__})")

    await update.effective_message.reply_text("\n".join(["✅ admin_health"] + checks))


@require_role(Role.MODERATOR)
async def admin_logs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = context.application.bot_data["config"]
    path = getattr(cfg, "log_file", "")
    if not path:
        await update.effective_message.reply_text("❌ LOG_FILE is not set")
        return

    text = read_last_lines(path, max_lines=120, max_bytes=64 * 1024)
    if not text:
        await update.effective_message.reply_text("Лог пустой или файл не найден.")
        return

    # Telegram message limit is ~4096 chars; keep headroom.
    if len(text) > 3500:
        text = text[-3500:]
        text = "(truncated)\n" + text
    await update.effective_message.reply_text(text)


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
        regs = [r for r in regs if r.status not in ("cancelled", "canceled")]
        confirmed = len([r for r in regs if r.status == "confirmed"])
        total_reg += len(regs)
        total_confirm += confirmed
        lines.append(f"{ev.name}: {len(regs)} (✅ {confirmed}, ❌ {len(regs)-confirmed})")
    text = "Статистика:\n" + "\n".join(lines) if lines else "Нет мероприятий"
    text += f"\n\nВсего: {total_reg}, подтвердили: {total_confirm}"
    await query.edit_message_text(text, reply_markup=admin_panel_kb())


@require_role(Role.MODERATOR)
async def export_regs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Heavy dependency: import lazily to keep bot startup fast on weak VPS.
    import pandas as pd

    query = update.callback_query
    await query.answer()
    profile_service = context.application.bot_data["profile_service"]
    user_repo = profile_service.user_repo
    event_service = context.application.bot_data["event_service"]
    users = await profile_service.list_users()
    user_by_id = {u.user_id: u for u in users}
    data = []
    events = await event_service.event_repo.list_events()
    for ev in events:
        regs = await event_service.list_registrations(ev.event_id)
        for reg in regs:
            user = user_by_id.get(reg.user_id) or await user_repo.get_user(reg.user_id)
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
    # Heavy dependency: import lazily to keep bot startup fast on weak VPS.
    import pandas as pd

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
    raw = update.message.text.strip()
    # Be tolerant to a common typo: YYYY-MM.DD HH:MM (dot between month and day)
    candidate = raw
    if len(raw) >= 16 and raw[7:8] == "." and raw[:7].count("-") == 1:
        # Example: 2026-02.12 12:00 -> 2026-02-12 12:00
        candidate = raw[:7] + "-" + raw[8:]
    try:
        datetime.strptime(candidate, "%Y-%m-%d %H:%M")
    except ValueError:
        await update.message.reply_text(
            "❌ Дата должна быть в формате YYYY-MM-DD HH:MM\n"
            "Например: 2026-02-12 12:00"
        )
        return Conversation.WAITING_EVENT_DATETIME

    context.user_data["new_event_dt"] = candidate
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
        # If something went wrong (e.g. date format), guide user back to the right step.
        msg = str(exc)
        await update.message.reply_text(f"❌ {msg}")
        if "Дата должна быть" in msg:
            await update.message.reply_text("Введите дату и время (YYYY-MM-DD HH:MM):")
            return Conversation.WAITING_EVENT_DATETIME
        if "Количество мест" in msg:
            await update.message.reply_text("Введите число мест:")
            return Conversation.WAITING_EVENT_SEATS
        return Conversation.WAITING_EVENT_NAME
    await update.message.reply_text(f"✅ Добавлено: {ev.name}")
    logger and logger.info(
        "Admin %s created event id=%s name=%s seats=%s",
        update.effective_user.id,
        getattr(ev, "event_id", None),
        ev.name,
        ev.max_seats,
    )
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
    logger and logger.info(
        "Admin %s updated event %s field=%s", update.effective_user.id, event_id, field
    )
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
    logger and logger.info("Admin %s deleted event %s", query.from_user.id, event_id)


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
    target = [r for r in regs if r.status not in ("confirmed", "cancelled", "canceled")]
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
    logger and logger.info("Reminder sent for event %s to %s users", event_id, sent)


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
    logger and logger.info("Broadcast to all finished by user_id=%s delivered=%s", query.from_user.id, sent)
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
    regs = [r for r in regs if r.status not in ("cancelled", "canceled")]
    sent = 0
    for reg in regs:
        try:
            await context.bot.send_message(chat_id=reg.user_id, text=text)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception as exc:  # noqa: BLE001
            logger and logger.warning("Broadcast event fail %s: %s", reg.user_id, exc)
    await query.edit_message_text(f"Рассылка по событию завершена. Доставлено: {sent}", reply_markup=admin_panel_kb())
    logger and logger.info(
        "Broadcast to event %s finished by user_id=%s delivered=%s", event_id, query.from_user.id, sent
    )
    return ConversationHandler.END


# Node CMS
async def _node_cms_render(update: Update, context: ContextTypes.DEFAULT_TYPE, query):
    node_service = context.application.bot_data["node_service"]
    # Show root nodes (where parent_id is NULL)
    nodes = await node_service.get_children(None)

    rows = [[InlineKeyboardButton(f"📁 {n.title}", callback_data=f"adm_node_view_{n.id}")] for n in nodes]
    rows.append([InlineKeyboardButton("➕ Добавить корневой раздел", callback_data="adm_node_add_none")])
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="admin_panel")])

    text = "Управление контентом и меню.\nВыберите раздел для редактирования или добавьте новый."
    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(rows))


@require_role(Role.ADMIN)
async def node_cms_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    await _node_cms_render(update, context, query)


async def _adm_node_view_render(update: Update, context: ContextTypes.DEFAULT_TYPE, node_id: int):
    query = update.callback_query
    if not query:
        return

    node_service = context.application.bot_data["node_service"]
    node = await node_service.get_node(node_id)
    children = await node_service.get_children(node_id)

    # В админке показываем контент "как есть" без Markdown-рендеринга:
    # иначе любой невалидный Markdown в node.content ломает edit_message_text,
    # и визуально выглядит как "не работает кнопка назад".
    parent_label = node.parent_id if node.parent_id is not None else "корень"
    text = (
        f"📍 Раздел: {node.title} (ID: {node.id})\n"
        f"⬆️ Родитель: {parent_label}\n"
        f"🔑 Ключ: {node.key or 'нет'}\n"
        f"🔗 URL: {node.url or 'нет'}\n"
        f"🔢 Порядок: {node.order_index}\n"
        f"🏠 Главное меню: {'да' if node.is_main_menu else 'нет'}\n\n"
        f"📝 Текст:\n{node.content}"
    )

    rows = []
    # Children
    for child in children:
        rows.append([InlineKeyboardButton(f"  └ {child.title}", callback_data=f"adm_node_view_{child.id}")])

    rows.append([InlineKeyboardButton("➕ Добавить подраздел", callback_data=f"adm_node_add_{node_id}")])
    rows.append([
        InlineKeyboardButton("✏️ Текст/Назв", callback_data=f"adm_node_edit_{node_id}"),
        InlineKeyboardButton("↗️ Перенести", callback_data=f"adm_node_reparent_{node_id}"),
        InlineKeyboardButton("🗑 Удалить", callback_data=f"adm_node_del_{node_id}")
    ])

    if node.parent_id is not None:
        rows.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"adm_node_view_{node.parent_id}")])
    else:
        rows.append([InlineKeyboardButton("⬅️ В начало", callback_data="admin_cms")])

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(rows),
        disable_web_page_preview=True,
    )


def _collect_descendants(root_id: int, nodes) -> set[int]:
    tree: dict[int | None, list] = {}
    for n in nodes:
        tree.setdefault(n.parent_id, []).append(n)
    descendants: set[int] = set()
    stack = [root_id]
    while stack:
        current = stack.pop()
        for child in tree.get(current, []):
            if child.id is None or child.id in descendants:
                continue
            descendants.add(child.id)
            stack.append(child.id)
    descendants.discard(root_id)
    return descendants


@require_role(Role.ADMIN)
async def adm_node_reparent_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    node_id = int(query.data.replace("adm_node_reparent_", ""))
    node_service = context.application.bot_data["node_service"]
    nodes = await node_service.get_all_nodes()
    descendants = _collect_descendants(node_id, nodes)

    keyboard: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton("⬆️ В корень", callback_data=f"adm_node_reparent_pick_{node_id}_root")]
    ]
    for n in nodes:
        if n.id in (None, node_id) or n.id in descendants:
            continue
        keyboard.append(
            [InlineKeyboardButton(f"{n.title} (id={n.id})", callback_data=f"adm_node_reparent_pick_{node_id}_{n.id}")]
        )
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"adm_node_view_{node_id}")])
    await query.edit_message_text("Выберите новый родитель для раздела:", reply_markup=InlineKeyboardMarkup(keyboard))


@require_role(Role.ADMIN)
async def adm_node_reparent_apply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    payload = query.data.replace("adm_node_reparent_pick_", "")
    parts = payload.split("_", 1)
    node_id = int(parts[0])
    parent_raw = parts[1] if len(parts) > 1 else "root"
    parent_id = None if parent_raw == "root" else int(parent_raw)

    node_service = context.application.bot_data["node_service"]
    node = await node_service.get_node(node_id)
    if not node:
        await query.edit_message_text("Раздел не найден.")
        return ConversationHandler.END

    await node_service.save_node(
        node_id=node.id,
        parent_id=parent_id,
        key=node.key,
        title=node.title,
        content=node.content,
        url=node.url,
        order_index=node.order_index,
        is_main_menu=node.is_main_menu,
    )
    context.application.bot_data.pop("main_menu_cache", None)
    await query.edit_message_text("✅ Сохранено. Обновляю структуру...")
    await _adm_node_view_render(update, context, node_id)
    return ConversationHandler.END


@require_role(Role.ADMIN)
async def adm_node_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    node_id = int(query.data.replace("adm_node_view_", ""))
    await _adm_node_view_render(update, context, node_id)


@require_role(Role.ADMIN)
async def adm_node_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Clear previous CMS data
    _clear_cms_draft(context)
        
    parent_id = query.data.replace("adm_node_add_", "")
    context.user_data["cms_parent_id"] = int(parent_id) if parent_id != "none" else None
    
    await query.edit_message_text("Введите заголовок кнопки:", reply_markup=cancel_keyboard())
    return Conversation.NODE_EDIT_TITLE


@require_role(Role.ADMIN)
async def adm_node_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    node_id = int(query.data.replace("adm_node_edit_", ""))
    
    node_service = context.application.bot_data["node_service"]
    node = await node_service.get_node(node_id)
    
    context.user_data["cms_node_id"] = node_id
    context.user_data["cms_parent_id"] = node.parent_id
    context.user_data["cms_key"] = node.key
    context.user_data["cms_title"] = node.title
    context.user_data["cms_content"] = node.content
    context.user_data["cms_url"] = node.url
    context.user_data["cms_order"] = node.order_index
    context.user_data["cms_is_main"] = node.is_main_menu
    
    await query.edit_message_text(
        f"Текущий заголовок: {node.title}\nВведите новый или /skip:",
        reply_markup=cancel_keyboard(),
    )
    return Conversation.NODE_EDIT_TITLE


async def adm_node_title_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text != "/skip":
        context.user_data["cms_title"] = text
    
    await update.message.reply_text(
        "Введите текст сообщения (поддерживается Markdown) или /skip:",
        reply_markup=cancel_keyboard(),
    )
    return Conversation.NODE_EDIT_CONTENT


async def adm_node_content_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text != "/skip":
        context.user_data["cms_content"] = text
    
    await update.message.reply_text(
        "Введите URL (если кнопка должна открывать ссылку) или /none или /skip:",
        reply_markup=cancel_keyboard(),
    )
    return Conversation.NODE_EDIT_URL


async def adm_node_url_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/none":
        context.user_data["cms_url"] = None
    elif text != "/skip":
        context.user_data["cms_url"] = text
    
    await update.message.reply_text(
        "Введите порядок сортировки (число) или /skip:",
        reply_markup=cancel_keyboard(),
    )
    return Conversation.NODE_EDIT_ORDER


async def adm_node_order_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text != "/skip":
        try:
            context.user_data["cms_order"] = int(text)
        except ValueError:
            await update.message.reply_text("Введите число!")
            return Conversation.NODE_EDIT_ORDER
            
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Да", callback_data="adm_node_is_main_yes"),
         InlineKeyboardButton("❌ Нет", callback_data="adm_node_is_main_no")],
        [InlineKeyboardButton("⏩ Пропустить", callback_data="adm_node_is_main_skip")],
        [InlineKeyboardButton("❌ Отмена", callback_data="adm_node_cancel")],
    ])
    await update.message.reply_text("Показывать в главном меню (Reply Keyboard)?", reply_markup=kb)
    return Conversation.NODE_EDIT_IS_MAIN


async def adm_node_is_main_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "adm_node_is_main_yes":
        context.user_data["cms_is_main"] = True
    elif query.data == "adm_node_is_main_no":
        context.user_data["cms_is_main"] = False
        
    node_service = context.application.bot_data["node_service"]
    await node_service.save_node(
        node_id=context.user_data.get("cms_node_id"),
        parent_id=context.user_data.get("cms_parent_id"),
        key=context.user_data.get("cms_key"),
        title=context.user_data.get("cms_title"),
        content=context.user_data.get("cms_content", "Пусто"),
        url=context.user_data.get("cms_url"),
        order_index=context.user_data.get("cms_order", 0),
        is_main_menu=context.user_data.get("cms_is_main", False)
    )
    
    # Invalidate main menu cache
    context.application.bot_data.pop("main_menu_cache", None)
    
    await query.edit_message_text("✅ Сохранено!")
    # Clear user data
    for key in ["cms_node_id", "cms_parent_id", "cms_title", "cms_content", "cms_url", "cms_order", "cms_is_main"]:
        context.user_data.pop(key, None)
        
    await node_cms_start(update, context)
    return ConversationHandler.END


@require_role(Role.ADMIN)
async def adm_node_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    node_id = int(query.data.replace("adm_node_del_", ""))
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Да, удалить", callback_data=f"adm_node_del_confirm_{node_id}")],
        [InlineKeyboardButton("❌ Отмена", callback_data=f"adm_node_view_{node_id}")]
    ])
    await query.edit_message_text("⚠️ Вы уверены? Это удалит также все подразделы!", reply_markup=kb)


@require_role(Role.ADMIN)
async def adm_node_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    node_id = int(query.data.replace("adm_node_del_confirm_", ""))
    
    node_service = context.application.bot_data["node_service"]
    node = await node_service.get_node(node_id)
    parent_id = node.parent_id if node else None
    
    await node_service.delete_node(node_id)
    # Invalidate main menu cache
    context.application.bot_data.pop("main_menu_cache", None)
    
    await query.edit_message_text("🗑 Удалено")
    
    if parent_id is not None:
        await _adm_node_view_render(update, context, parent_id)
    else:
        await _node_cms_render(update, context, query)
    return ConversationHandler.END


# Roles
@require_role(Role.ADMIN)


@require_role(Role.ADMIN)
async def admin_add_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("??????? ???????? user_id ?????? ??????:", reply_markup=cancel_keyboard())
    return Conversation.ADMIN_ADD_ID


@require_role(Role.ADMIN)
async def admin_add_admin_apply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = int(update.message.text.strip())
    except Exception:
        await update.message.reply_text("??????? ?????????? user_id (?????).", reply_markup=cancel_keyboard())
        return Conversation.ADMIN_ADD_ID

    profile_service = context.application.bot_data["profile_service"]
    cfg = context.application.bot_data.get("config")
    await profile_service.ensure_user(user_id, username="", full_name=f"admin-{user_id}")
    await profile_service.assign_role(user_id, Role.ADMIN)
    if cfg and user_id not in cfg.admin_ids:
        cfg.admin_ids.append(user_id)
    await update.message.reply_text("? ????? ????????.", reply_markup=admin_panel_kb())
    return ConversationHandler.END
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
            # ВАЖНО: не полагаемся на context.user_data, потому что при нескольких
            # одновременно запущенных инстансах бота (409 Conflict) callback может
            # обработать другой процесс и user_data будет пустой.
            [InlineKeyboardButton("admin", callback_data=f"role_set_admin_{uid}")],
            [InlineKeyboardButton("moderator", callback_data=f"role_set_moderator_{uid}")],
            [InlineKeyboardButton("user", callback_data=f"role_set_user_{uid}")],
        ]
    )
    await query.edit_message_text("Выберите роль:", reply_markup=kb)


@require_role(Role.ADMIN)
async def role_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    payload = query.data.replace("role_set_", "")
    # Поддерживаем оба формата:
    # - новый: role_set_<role>_<user_id>
    # - старый: role_set_<role> (user_id берём из user_data)
    parts = payload.split("_", 1)
    role_name = parts[0]
    uid = None
    if len(parts) == 2:
        try:
            uid = int(parts[1])
        except ValueError:
            uid = None
    if uid is None:
        uid = context.user_data.get("role_user_id")
    if uid is None:
        await query.edit_message_text("❌ Не удалось определить пользователя. Откройте назначение роли заново.", reply_markup=admin_panel_kb())
        return
    profile_service = context.application.bot_data["profile_service"]
    await profile_service.assign_role(uid, Role(role_name))
    await query.edit_message_text("Роль обновлена", reply_markup=admin_panel_kb())
    logger and logger.info("Admin %s set role %s for user %s", query.from_user.id, role_name, uid)


@require_role(Role.ADMIN)
async def reload_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    restart_service = context.application.bot_data["restart_service"]
    await restart_service.reload_data(context)
    await query.edit_message_text("Данные перечитаны", reply_markup=admin_panel_kb())
    logger and logger.info("Admin %s requested data reload", query.from_user.id)


@require_role(Role.ADMIN)
async def restart_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    restart_service = context.application.bot_data["restart_service"]
    await restart_service.schedule_restart(update, context)
    logger and logger.info("Admin %s requested restart", query.from_user.id)


async def admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено.", reply_markup=admin_panel_kb())
    return ConversationHandler.END


@require_role(Role.ADMIN)
async def adm_node_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel Node CMS add/edit flow and return to CMS root."""
    query = update.callback_query
    if query:
        await query.answer()

    # Clear CMS draft data
    _clear_cms_draft(context)

    if query:
        await query.edit_message_text("Отменено.")
    else:
        await update.message.reply_text("Отменено.")

    await node_cms_start(update, context)
    return ConversationHandler.END


@require_role(Role.ADMIN)
async def adm_node_view_from_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Allow navigation callbacks while a Node CMS conversation is active."""
    _clear_cms_draft(context)
    await adm_node_view(update, context)
    return ConversationHandler.END


@require_role(Role.ADMIN)
async def node_cms_start_from_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Allow returning to CMS root while a Node CMS conversation is active."""
    _clear_cms_draft(context)
    await node_cms_start(update, context)
    return ConversationHandler.END


@require_role(Role.ADMIN)
async def admin_panel_from_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Allow returning to admin panel while a conversation is active."""
    _clear_cms_draft(context)
    await admin_panel(update, context)
    return ConversationHandler.END


def setup_handlers(application):
    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Command("admin"), admin_login),
            CallbackQueryHandler(add_event_start, pattern="^admin_add_event$"),
            CallbackQueryHandler(edit_event_field, pattern="^admin_edit_field_.*$"),
            CallbackQueryHandler(broadcast_all_start, pattern="^admin_broadcast_all$"),
            CallbackQueryHandler(broadcast_event_start, pattern="^admin_broadcast_event$"),
            CallbackQueryHandler(broadcast_event_pick, pattern="^admin_broadcast_pick_.*$"),
            CallbackQueryHandler(adm_node_add, pattern="^adm_node_add_.*$"),
            CallbackQueryHandler(adm_node_edit, pattern="^adm_node_edit_.*$"),
            CallbackQueryHandler(admin_add_admin_start, pattern="^admin_add_admin$"),
        ],
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
            # Node CMS states
            Conversation.NODE_EDIT_TITLE: [
                CallbackQueryHandler(adm_node_cancel, pattern="^adm_node_cancel$"),
                CallbackQueryHandler(adm_node_view_from_conv, pattern="^adm_node_view_.*$"),
                CallbackQueryHandler(node_cms_start_from_conv, pattern="^admin_cms$"),
                CallbackQueryHandler(admin_panel_from_conv, pattern="^admin_panel$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND | filters.Regex("^/skip$"), adm_node_title_input),
            ],
            Conversation.NODE_EDIT_CONTENT: [
                CallbackQueryHandler(adm_node_cancel, pattern="^adm_node_cancel$"),
                CallbackQueryHandler(adm_node_view_from_conv, pattern="^adm_node_view_.*$"),
                CallbackQueryHandler(node_cms_start_from_conv, pattern="^admin_cms$"),
                CallbackQueryHandler(admin_panel_from_conv, pattern="^admin_panel$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND | filters.Regex("^/skip$"), adm_node_content_input),
            ],
            Conversation.NODE_EDIT_URL: [
                CallbackQueryHandler(adm_node_cancel, pattern="^adm_node_cancel$"),
                CallbackQueryHandler(adm_node_view_from_conv, pattern="^adm_node_view_.*$"),
                CallbackQueryHandler(node_cms_start_from_conv, pattern="^admin_cms$"),
                CallbackQueryHandler(admin_panel_from_conv, pattern="^admin_panel$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND | filters.Regex("^/(skip|none)$"), adm_node_url_input),
            ],
            Conversation.NODE_EDIT_ORDER: [
                CallbackQueryHandler(adm_node_cancel, pattern="^adm_node_cancel$"),
                CallbackQueryHandler(adm_node_view_from_conv, pattern="^adm_node_view_.*$"),
                CallbackQueryHandler(node_cms_start_from_conv, pattern="^admin_cms$"),
                CallbackQueryHandler(admin_panel_from_conv, pattern="^admin_panel$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND | filters.Regex("^/skip$"), adm_node_order_input),
            ],
            Conversation.ADMIN_ADD_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_admin_apply)],
            Conversation.NODE_EDIT_IS_MAIN: [
                CallbackQueryHandler(adm_node_cancel, pattern="^adm_node_cancel$"),
                CallbackQueryHandler(adm_node_view_from_conv, pattern="^adm_node_view_.*$"),
                CallbackQueryHandler(node_cms_start_from_conv, pattern="^admin_cms$"),
                CallbackQueryHandler(admin_panel_from_conv, pattern="^admin_panel$"),
                CallbackQueryHandler(adm_node_is_main_input, pattern="^adm_node_is_main_.*$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel), CallbackQueryHandler(adm_node_cancel, pattern="^adm_node_cancel$")],
        per_user=True,
    )
    application.add_handler(conv)
    application.add_handler(MessageHandler(filters.Regex(f"^{ADMIN_BUTTON_TEXT}$"), admin_entry))
    application.add_handler(CommandHandler("admin_status", admin_status_cmd))
    application.add_handler(CommandHandler("admin_health", admin_health_cmd))
    application.add_handler(CommandHandler("admin_logs", admin_logs_cmd))
    application.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    application.add_handler(CallbackQueryHandler(stats, pattern="^admin_stats$"))
    application.add_handler(CallbackQueryHandler(export_regs, pattern="^admin_export_regs$"))
    application.add_handler(CallbackQueryHandler(export_users, pattern="^admin_export_users$"))
    application.add_handler(CallbackQueryHandler(edit_event_start, pattern="^admin_edit_event$"))
    application.add_handler(CallbackQueryHandler(edit_event_pick, pattern="^admin_edit_pick_.*$"))
    application.add_handler(CallbackQueryHandler(delete_event_start, pattern="^admin_delete_event$"))
    application.add_handler(CallbackQueryHandler(delete_event_confirm, pattern="^admin_delete_pick_.*$"))
    application.add_handler(CallbackQueryHandler(delete_event_go, pattern="^admin_delete_go_.*$"))
    application.add_handler(CallbackQueryHandler(remind_unconfirmed, pattern="^admin_remind$"))
    application.add_handler(CallbackQueryHandler(remind_send, pattern="^admin_remind_pick_.*$"))
    
    # Node CMS
    application.add_handler(CallbackQueryHandler(node_cms_start, pattern="^admin_cms$"))
    application.add_handler(CallbackQueryHandler(node_cms_start, pattern="^admin_menu$"))
    application.add_handler(CallbackQueryHandler(adm_node_view, pattern="^adm_node_view_.*$"))
    application.add_handler(CallbackQueryHandler(adm_node_reparent_start, pattern="^adm_node_reparent_.*$"))
    application.add_handler(CallbackQueryHandler(adm_node_reparent_apply, pattern="^adm_node_reparent_pick_.*$"))
    application.add_handler(CallbackQueryHandler(adm_node_delete, pattern=r"^adm_node_del_(\d+)$"))
    application.add_handler(CallbackQueryHandler(adm_node_delete_confirm, pattern="^adm_node_del_confirm_.*$"))
    
    application.add_handler(CallbackQueryHandler(roles_start, pattern="^admin_roles$"))
    application.add_handler(CallbackQueryHandler(role_pick, pattern="^role_pick_.*$"))
    application.add_handler(CallbackQueryHandler(role_set, pattern="^role_set_.*$"))
    application.add_handler(CallbackQueryHandler(reload_data, pattern="^admin_reload$"))
    application.add_handler(CallbackQueryHandler(restart_bot, pattern="^admin_restart$"))

