from __future__ import annotations

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
)

from ..constants import Conversation
from ..services.messaging import send_main_menu
from ..utils.errors import ValidationError


def _event_keyboard(events):
    rows = []
    for ev in events:
        rows.append([InlineKeyboardButton(f"{ev.name}", callback_data=f"event_view_{ev.event_id}")])
    return InlineKeyboardMarkup(rows)


async def list_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    event_service = context.application.bot_data["event_service"]
    events = await event_service.list_active_events()
    if not events:
        await update.message.reply_text("Нет активных мероприятий сейчас.")
        return
    await update.message.reply_text("Доступные мероприятия:", reply_markup=_event_keyboard(events))


async def list_my_registrations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile_service = context.application.bot_data["profile_service"]
    event_service = context.application.bot_data["event_service"]

    profile = await profile_service.get_profile(update.effective_user.id)
    if not profile or not profile.consent:
        await update.message.reply_text("Необходимо согласие на обработку ПДн. Нажмите /start.")
        return

    regs = await event_service.list_user_registrations(update.effective_user.id, only_active=True)
    if not regs:
        await update.message.reply_text("У вас нет активных регистраций.")
        return

    rows = []
    for reg in regs:
        ev = await event_service.get_event(reg.event_id)
        if not ev:
            continue
        status = "✅" if reg.status == "confirmed" else "🕓"
        rows.append([InlineKeyboardButton(f"{status} {ev.name} ({ev.datetime_str})", callback_data=f"event_view_{ev.event_id}")])
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="events_back")])
    await update.message.reply_text("Ваши регистрации:", reply_markup=InlineKeyboardMarkup(rows))


async def view_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    event_id = query.data.replace("event_view_", "")
    event_service = context.application.bot_data["event_service"]
    event = await event_service.get_event(event_id)
    if not event:
        await query.edit_message_text("Мероприятие не найдено.")
        return
    regs = await event_service.list_registrations(event_id)
    active_regs = [r for r in regs if r.status not in ("cancelled", "canceled")]
    free = event.max_seats - len(active_regs)

    user_reg = await event_service.get_user_registration(query.from_user.id, event_id)
    user_status = "—"
    actions = []
    if not user_reg or user_reg.status in ("cancelled", "canceled"):
        actions.append([InlineKeyboardButton("📝 Зарегистрироваться", callback_data=f"event_register_{event_id}")])
    else:
        user_status = user_reg.status
        if user_reg.status != "confirmed":
            actions.append([InlineKeyboardButton("✅ Подтвердить участие", callback_data=f"event_confirm_{event_id}")])
        actions.append([InlineKeyboardButton("❌ Отменить регистрацию", callback_data=f"event_cancel_{event_id}")])

    actions.append([InlineKeyboardButton("⬅️ Назад", callback_data="events_back")])
    kb = InlineKeyboardMarkup(actions)
    text = (
        f"📌 {event.name}\n"
        f"📅 {event.datetime_str}\n"
        f"📝 {event.description}\n"
        f"Ваш статус: {user_status}\n"
        f"Свободно мест: {free}/{event.max_seats}"
    )
    await query.edit_message_text(text, reply_markup=kb)


async def start_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    event_id = query.data.replace("event_register_", "")
    profile_service = context.application.bot_data["profile_service"]
    event_service = context.application.bot_data["event_service"]

    event = await event_service.get_event(event_id)
    if not event:
        await query.edit_message_text("Мероприятие не найдено.")
        return ConversationHandler.END

    profile = await profile_service.get_profile(query.from_user.id)
    if not profile or not profile.consent:
        await query.edit_message_text("Требуется согласие на ПДн и профиль. Нажмите /start.")
        return ConversationHandler.END

    context.user_data["pending_event"] = event_id
    # Collect missing data
    if not profile.full_name:
        await query.edit_message_text("Введите ваше ФИО для профиля:")
        context.user_data["registration_flow"] = "name"
        return Conversation.INPUT_NAME
    if not profile.email:
        await query.edit_message_text("Введите ваш email:")
        context.user_data["registration_flow"] = "email"
        return Conversation.INPUT_EMAIL

    return await confirm_registration(query.message, context, profile.full_name, profile.email, event)


async def confirm_registration(messageable, context, full_name, email, event):
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Подтвердить", callback_data=f"event_confirm_{event.event_id}")],
            [InlineKeyboardButton("❌ Отмена", callback_data="events_back")],
        ]
    )
    context.user_data["pending_data"] = {"name": full_name, "email": email}
    chat_id = (
        messageable.chat_id
        if hasattr(messageable, "chat_id")
        else messageable.chat.id  # type: ignore[attr-defined]
    )
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"Проверьте данные:\nФИО: {full_name}\nEmail: {email}\n\nСобытие: {event.name}",
        reply_markup=kb,
    )
    return ConversationHandler.END


async def collect_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile_service = context.application.bot_data["profile_service"]
    try:
        await profile_service.update_full_name(update.effective_user.id, update.message.text)
    except ValidationError as exc:
        await update.message.reply_text(f"❌ {exc}")
        return Conversation.INPUT_NAME
    # continue flow
    profile = await profile_service.get_profile(update.effective_user.id)
    if not profile.email:
        await update.message.reply_text("Введите ваш email:")
        context.user_data["registration_flow"] = "email"
        return Conversation.INPUT_EMAIL
    event_id = context.user_data.get("pending_event")
    event_service = context.application.bot_data["event_service"]
    event = await event_service.get_event(event_id)
    if not event:
        await update.message.reply_text("Мероприятие не найдено.")
        return ConversationHandler.END
    return await confirm_registration(update.message, context, profile.full_name, profile.email, event)


async def collect_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile_service = context.application.bot_data["profile_service"]
    try:
        await profile_service.update_email(update.effective_user.id, update.message.text)
    except ValidationError as exc:
        await update.message.reply_text(f"❌ {exc}")
        return Conversation.INPUT_EMAIL
    profile = await profile_service.get_profile(update.effective_user.id)
    event_id = context.user_data.get("pending_event")
    event_service = context.application.bot_data["event_service"]
    event = await event_service.get_event(event_id)
    if not event:
        await update.message.reply_text("Мероприятие не найдено.")
        return ConversationHandler.END
    return await confirm_registration(update.message, context, profile.full_name, profile.email, event)


async def confirm_registration_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    event_id = query.data.replace("event_confirm_", "")
    event_service = context.application.bot_data["event_service"]
    try:
        await event_service.confirm_or_register(query.from_user.id, event_id)
    except ValidationError as exc:
        await query.edit_message_text(f"❌ {exc}")
        return ConversationHandler.END
    event = await event_service.get_event(event_id)
    await query.edit_message_text(f"✅ Участие подтверждено: {event.name}")
    await send_main_menu(context, query.from_user.id)
    return ConversationHandler.END


async def cancel_registration_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    event_id = query.data.replace("event_cancel_", "")
    event_service = context.application.bot_data["event_service"]
    try:
        await event_service.cancel_registration(query.from_user.id, event_id)
    except ValidationError as exc:
        await query.edit_message_text(f"❌ {exc}")
        return ConversationHandler.END
    event = await event_service.get_event(event_id)
    await query.edit_message_text(f"🗑 Регистрация отменена: {event.name if event else event_id}")
    await send_main_menu(context, query.from_user.id)
    return ConversationHandler.END


async def back_from_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await send_main_menu(context, query.from_user.id)
    return ConversationHandler.END


def setup_handlers(application):
    conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_registration, pattern="^event_register_.*$"),
        ],
        states={
            Conversation.INPUT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_name)],
            Conversation.INPUT_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_email)],
        },
        fallbacks=[],
        per_user=True,
    )
    application.add_handler(conv)
    # Основные пункты меню обрабатываются роутером, но оставляем хендлеры совместимости.
    application.add_handler(MessageHandler(filters.Regex("^📋 Мероприятия$"), list_events))
    application.add_handler(MessageHandler(filters.Regex("^🗓 Мои регистрации$"), list_my_registrations))
    application.add_handler(CallbackQueryHandler(view_event, pattern="^event_view_.*$"))
    application.add_handler(CallbackQueryHandler(confirm_registration_callback, pattern="^event_confirm_.*$"))
    application.add_handler(CallbackQueryHandler(cancel_registration_callback, pattern="^event_cancel_.*$"))
    application.add_handler(CallbackQueryHandler(back_from_events, pattern="^events_back$"))

