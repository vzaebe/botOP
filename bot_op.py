import re
import os
import json
import asyncio
from io import BytesIO
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Document
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
import pandas as pd

# --- Настройки ---
TOKEN = "8085894044:AAHtlk0D299yJfDt_tqKY2iLrPNWV0bB5zI"
ADMIN_ID = 7265626871
ADMIN_PASSWORD = "123"

# --- Файлы ---
EVENTS_FILE = "events.xlsx"
REGISTRATIONS_FILE = "registrations.xlsx"
TEMPLATE_DIR = "templates"
EVENTS_TEMPLATE = os.path.join(TEMPLATE_DIR, "events_template.xlsx")

# --- Состояния ---
INPUT_NAME, INPUT_EMAIL, WAITING_ADMIN_PASSWORD = range(3)
WAITING_EVENT_NAME, WAITING_EVENT_DATETIME, WAITING_EVENT_DESC, WAITING_EVENT_SEATS = range(4, 8)
WAITING_BROADCAST_MESSAGE, WAITING_BROADCAST_CONFIRM = 8, 9
WAITING_EVENT_BROADCAST_MESSAGE, WAITING_EVENT_BROADCAST_CONFIRM = 10, 11

# --- Глобальные переменные ---
all_bot_users = {}
USERS_FILE = "bot_users.json"

def save_bot_users():
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(all_bot_users, f, ensure_ascii=False, indent=4)

def load_bot_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for uid_str, info in data.items():
                all_bot_users[int(uid_str)] = info  # user_id — int

# --- Инициализация файлов ---
def init_files():
    if not os.path.exists(TEMPLATE_DIR):
        os.makedirs(TEMPLATE_DIR)
    if not os.path.exists(EVENTS_TEMPLATE):
        df = pd.DataFrame(columns=["event_id", "name", "datetime_str", "desc", "max_seats"])
        df.to_excel(EVENTS_TEMPLATE, index=False)
    if not os.path.exists(EVENTS_FILE):
        pd.read_excel(EVENTS_TEMPLATE).to_excel(EVENTS_FILE, index=False)
    if not os.path.exists(REGISTRATIONS_FILE):
        df = pd.DataFrame(columns=[
            "user_id", "name", "email", "event_id", "event_name", "reg_time", "status"
        ])
        df["status"] = "registered"
        df.to_excel(REGISTRATIONS_FILE, index=False)

# --- Загрузка данных ---
def load_events_from_excel():
    try:
        df = pd.read_excel(EVENTS_FILE)
        events = {}
        for _, row in df.iterrows():
            event_id = str(row["event_id"])
            events[event_id] = {
                "name": row["name"],
                "datetime_str": row["datetime_str"],
                "desc": row["desc"],
                "max_seats": int(row["max_seats"]),
                "registered_users": {}
            }
        return events
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return {}

def load_registrations():
    events = load_events_from_excel()
    for eid in events:
        events[eid]["registered_users"] = {}

    try:
        df = pd.read_excel(REGISTRATIONS_FILE)
        for _, row in df.iterrows():
            uid = int(row["user_id"])
            eid = str(row["event_id"])
            if eid in events:
                events[eid]["registered_users"][uid] = {
                    "name": row["name"],
                    "email": row["email"],
                    "status": row.get("status", "registered")
                }
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    return events

def save_registration(user_id, name, email, event_id, event_name):
    new_row = pd.DataFrame([{
        "user_id": user_id,
        "name": name,
        "email": email,
        "event_id": event_id,
        "event_name": event_name,
        "reg_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "registered"
    }])
    try:
        df = pd.read_excel(REGISTRATIONS_FILE)
        df = pd.concat([df, new_row], ignore_index=True)
    except:
        df = new_row
    df.to_excel(REGISTRATIONS_FILE, index=False)

def is_event_active(event):
    try:
        dt = datetime.strptime(event["datetime_str"], "%Y-%m-%d %H:%M")
        return dt > datetime.now()
    except:
        return False

# --- Клавиатуры ---
def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("📋 Мероприятия", callback_data="events")],
        [InlineKeyboardButton("🔗 Полезные ссылки", callback_data="links")],
        [InlineKeyboardButton("🎧 Подкасты", callback_data="podcasts")],
        [InlineKeyboardButton("📚 База знаний", callback_data="knowledge_base")],
        [InlineKeyboardButton("🏫 Учреждения", callback_data="educational_orgs")],
        [InlineKeyboardButton("🤫 Работа с глухими", callback_data="tips_deaf")],
        [InlineKeyboardButton("👤 Представление", callback_data="tips_intro")],
        [InlineKeyboardButton("💼 Практика", callback_data="internship")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_admin_menu():
    keyboard = [
        [InlineKeyboardButton("👥 Экспорт всех пользователей", callback_data="export_all_users")],
        [InlineKeyboardButton("📊 Экспорт участников меропр.", callback_data="export_all")],
        [InlineKeyboardButton("👥 Участники по меропр.", callback_data="view_registrations")],
        [InlineKeyboardButton("🔔 Напомнить о подтв.", callback_data="remind_unconfirmed")],
        [InlineKeyboardButton("🎯 Рассылка по меропр.", callback_data="broadcast_event")],
        [InlineKeyboardButton("📩 Рассылка всем", callback_data="broadcast")],
        [InlineKeyboardButton("➕ Добавить меропр.", callback_data="add_event")],
        [InlineKeyboardButton("✏️ Редактировать меропр.", callback_data="edit_event")],
        [InlineKeyboardButton("🗑 Удалить меропр.", callback_data="delete_event")],
        [InlineKeyboardButton("🔄 Обновить меропр.", callback_data="reload_events")]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Информационные разделы ---
INFO_SECTIONS = {
    "links": {
        "title": "🔗 Полезные ссылки",
        "text": (
            "📌 Основные ресурсы:\n\n"
            "• [Союз глухих России](https://www.deaf.ru)\n"
            "• [Жестовый язык онлайн](https://ruslan.online)\n"
            "• [Проект «Живой звук»](https://живойзвук.рф)\n"
            "• [YouTube: Жестовый канал](https://youtube.com/c/SignLanguageRU)"
        )
    },
    "podcasts": {
        "title": "🎧 Подкасты",
        "text": (
            "🎙 Подкасты:\n\n"
            "• *«Глухие тоже говорят»*\n"
            "• *«Инклюзивно»*\n"
            "• *«Без звука»*\n\n"
            "Доступны на Spotify, Яндекс.Музыка"
        )
    },
    "knowledge_base": {
        "title": "📚 База знаний",
        "text": (
            "🧠 Что важно знать:\n\n"
            "• Глухота — не инвалидность мышления\n"
            "• Язык жестов — полноценный язык\n"
            "• Не все носят слуховые аппараты\n"
            "• Лучше спросить, как общаться"
        )
    },
    "educational_orgs": {
        "title": "🏫 Образовательные учреждения",
        "text": (
            "🎓 Для глухих:\n\n"
            "• Москва: Школа №576, Центр Сурдо\n"
            "• СПб: Лицей «Гармония»\n"
            "• Казань: Республиканская школа-интернат"
        )
    },
    "tips_deaf": {
        "title": "🤫 Работа с глухими",
        "text": (
            "🤝 Как взаимодействовать:\n\n"
            "1. Привлеките внимание\n"
            "2. Говорите чётко\n"
            "3. Не прикрывайте рот\n"
            "4. Можно писать в чат\n"
            "🚫 Не говорите за спиной"
        )
    },
    "tips_intro": {
        "title": "👤 Как представляться",
        "text": (
            "🙋‍♂️ Пример:\n\n"
            "«Меня зовут Алексей. Я психолог. "
            "Я хочу помочь. Вы поняли?»\n\n"
            "💡 Жест имени + профессия"
        )
    },
    "internship": {
        "title": "💼 Хочу на практику",
        "text": (
            "🎯 Мы принимаем студентов!\n\n"
            "📌 Условия:\n"
            "• Открытость\n"
            "• Желание помогать\n"
            "• Базовое знание ЖЯР\n\n"
            "📬 Пишите: info@inklyucheno.ru"
        )
    }
}

# --- Команды ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    full_name = f"{user.first_name} {user.last_name}".strip() if user.last_name else user.first_name

    # Сохраняем пользователя при первом запуске
    if user_id not in all_bot_users:
        all_bot_users[user_id] = {
            "name": full_name,
            "username": user.username or "",
            "first_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        save_bot_users()

    await update.message.reply_text(
        f"Привет, {full_name}! 👋\n\n"
        "Добро пожаловать в бот регистрации на мероприятия!",
        reply_markup=get_main_menu()
    )

# --- Информация ---
async def info_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data in INFO_SECTIONS:
        s = INFO_SECTIONS[data]
        text = f"📘 {s['title']}\n\n{s['text']}"
        kb = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]]
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Главное меню:", reply_markup=get_main_menu())

# --- Подтверждение участия ---
async def confirm_participation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    event_id = "_".join(q.data.split("_")[2:])
    events = context.bot_data["events"]
    if event_id not in events:
        await q.edit_message_text("❌ Не найдено.")
        return
    ev = events[event_id]
    uid = update.effective_user.id
    if uid not in ev["registered_users"]:
        await q.edit_message_text("Вы не зарегистрированы.")
        return
    try:
        df = pd.read_excel(REGISTRATIONS_FILE)
        mask = (df["user_id"] == uid) & (df["event_id"] == event_id)
        if mask.any():
            df.loc[mask, "status"] = "confirmed"
            df.to_excel(REGISTRATIONS_FILE, index=False)
            if uid in ev["registered_users"]:
                ev["registered_users"][uid]["status"] = "confirmed"
            await q.edit_message_text(f"✅ Спасибо за подтверждение!\n\n📌 {ev['name']}")
    except Exception as ex:
        await q.edit_message_text(f"❌ Ошибка: {ex}")

# --- Админ: вход ---
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid != ADMIN_ID:
        await update.message.reply_text("⛔ Нет доступа.")
        return ConversationHandler.END
    await update.message.reply_text("🔐 Введите пароль:")
    return WAITING_ADMIN_PASSWORD

async def check_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    p = update.message.text.strip()
    if p == ADMIN_PASSWORD:
        context.user_data["is_admin_authenticated"] = True
        await update.message.reply_text("✅ Вход выполнен.")
        await show_admin_panel(update, context)
    else:
        await update.message.reply_text("❌ Ошибка.")
    return ConversationHandler.END

async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    events = context.bot_data["events"]
    total = sum(len(e["registered_users"]) for e in events.values())

    stats = []
    for event_id, event in events.items():
        reg_count = len(event["registered_users"])
        # Подсчитаем, сколько подтвердили
        confirmed_count = 0
        for user_id, user_data in event["registered_users"].items():
            if user_data.get("status") == "confirmed":
                confirmed_count += 1
        not_confirmed = reg_count - confirmed_count
        stats.append(f"• {event['name']}: {reg_count} (✅ {confirmed_count}, ❌ {not_confirmed})")

    text = f"🔐 Админ-панель\n\n📊 Всего: {total}\n\n"
    text += "\n".join(stats) if stats else "Нет мероприятий"
    text += "\n\nВыберите действие:"

    await update.message.reply_text(text, reply_markup=get_admin_menu())

# --- Экспорт пользователей ---
async def export_all_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Проверка прав
    if update.effective_user.id != ADMIN_ID:
        await query.edit_message_text("⛔ У вас нет доступа.")
        return

    if not all_bot_users:
        await query.edit_message_text("📭 Нет пользователей.")
        return

    # Подготовка данных
    data = []
    for uid, info in all_bot_users.items():
        data.append({
            "user_id": uid,
            "name": info["name"],
            "username": f"@{info['username']}" if info["username"] else "",
            "first_seen": info["first_seen"]
        })

    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Пользователи бота")

    output.seek(0)

    await query.edit_message_text("📤 Формируем список всех пользователей...")
    try:
        await context.bot.send_document(
            chat_id=query.message.chat_id,
            document=output,
            filename="all_bot_users.xlsx",
            caption="📎 Все пользователи, которые использовали бот"
        )
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка отправки: {e}")

# --- Экспорт регистраций ---
async def export_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Проверка прав
    if update.effective_user.id != ADMIN_ID:
        await query.edit_message_text("⛔ Доступ запрещён.")
        return

    try:
        # Читаем все регистрации
        df = pd.read_excel(REGISTRATIONS_FILE)
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Регистрации")
        output.seek(0)

        await query.edit_message_text("📤 Формируем файл...")
        await context.bot.send_document(
            chat_id=query.message.chat_id,
            document=output,
            filename="registrations_export.xlsx",
            caption="📎 Все зарегистрированные участники"
        )
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка экспорта: {e}")

# --- РАССЫЛКА ВСЕМ ---
async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if update.effective_user.id != ADMIN_ID:
        await query.edit_message_text("⛔ Доступ запрещён.")
        return ConversationHandler.END

    await query.edit_message_text(
        "📬 Отправьте *текст* или *фото с подписью*, чтобы сделать рассылку всем пользователям бота."
    )
    return WAITING_BROADCAST_MESSAGE

async def receive_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["broadcast"] = {}

    if update.message.photo:
        context.user_data["broadcast"] = {
            "type": "photo",
            "file_id": update.message.photo[-1].file_id,
            "caption": update.message.caption or ""
        }
    elif update.message.text:
        context.user_data["broadcast"] = {
            "type": "text",
            "text": update.message.text
        }
    else:
        await update.message.reply_text("❌ Поддерживается только текст или фото с подписью.")
        return ConversationHandler.END

    # Предпросмотр
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Да, отправить", callback_data="confirm_broadcast")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_broadcast")]
    ])

    if context.user_data["broadcast"]["type"] == "photo":
        await update.message.reply_photo(
            photo=context.user_data["broadcast"]["file_id"],
            caption=f"📸 Рассылка:\n\n{context.user_data['broadcast']['caption']}\n\n"
                    f"📤 Всем ({len(all_bot_users)} пользователей)\n"
                    "Отправить?",
            reply_markup=kb
        )
    else:
        await update.message.reply_text(
            f"📬 Сообщение:\n\n{context.user_data['broadcast']['text']}\n\n"
            f"📤 Всем ({len(all_bot_users)} пользователей)\n"
            "Отправить?",
            reply_markup=kb,
            parse_mode="Markdown"
        )
    return WAITING_BROADCAST_CONFIRM

async def confirm_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = context.user_data.get("broadcast")
    if not data:
        await query.edit_message_text("❌ Ошибка: нет данных для рассылки.")
        return ConversationHandler.END

    await query.edit_message_text(f"📤 Начинаю рассылку {len(all_bot_users)} пользователям...")

    sent_count = 0
    failed_count = 0

    for user_id in all_bot_users:
        try:
            if data["type"] == "photo":
                await context.bot.send_photo(
                    chat_id=user_id,
                    photo=data["file_id"],
                    caption=data["caption"],
                    parse_mode="Markdown"
                )
            else:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=data["text"],
                    parse_mode="Markdown"
                )
            sent_count += 1
        except Exception as e:
            error_msg = str(e)
            if "Forbidden" in error_msg or "blocked" in error_msg:
                print(f"🚫 Пользователь {user_id} заблокировал бота")
            else:
                print(f"🔴 Ошибка при отправке {user_id}: {error_msg}")
            failed_count += 1

        await asyncio.sleep(0.05)  # Защита от лимитов

    await query.message.reply_text(
        f"✅ Рассылка завершена!\n\n"
        f"📬 Успешно: {sent_count}\n"
        f"❌ Ошибок: {failed_count}",
        reply_markup=get_admin_menu()
    )
    return ConversationHandler.END

async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ Рассылка отменена.", reply_markup=get_admin_menu())
    return ConversationHandler.END

# --- ДОБАВЛЕНИЕ МЕРОПРИЯТИЯ ---
async def start_add_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if update.effective_user.id != ADMIN_ID:
        await query.edit_message_text("⛔ Нет доступа.")
        return

    await query.edit_message_text("📝 Введите *название мероприятия*:", parse_mode="Markdown")
    return WAITING_EVENT_NAME

async def receive_event_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if len(name) < 3:
        await update.message.reply_text("❌ Слишком короткое название. Попробуйте снова:")
        return WAITING_EVENT_NAME

    context.user_data["new_event"] = {"name": name}
    await update.message.reply_text(
        "🕒 Введите дату и время в формате:\n\n*YYYY-MM-DD HH:MM*\n\nНапример: `2025-12-25 19:00`",
        parse_mode="Markdown"
    )
    return WAITING_EVENT_DATETIME

async def receive_event_datetime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    datetime_str = update.message.text.strip()
    try:
        datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
        context.user_data["new_event"]["datetime_str"] = datetime_str
        await update.message.reply_text("📄 Введите описание мероприятия:")
        return WAITING_EVENT_DESC
    except ValueError:
        await update.message.reply_text("❌ Неверный формат даты. Используйте: YYYY-MM-DD HH:MM")
        return WAITING_EVENT_DATETIME

async def receive_event_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    desc = update.message.text.strip()
    if len(desc) < 5:
        await update.message.reply_text("❌ Слишком короткое описание. Попробуйте снова:")
        return WAITING_EVENT_DESC

    context.user_data["new_event"]["desc"] = desc
    await update.message.reply_text("👥 Введите максимальное количество участников (число):")
    return WAITING_EVENT_SEATS

async def receive_event_seats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    seats_str = update.message.text.strip()
    if not seats_str.isdigit() or int(seats_str) <= 0:
        await update.message.reply_text("❌ Введите положительное число:")
        return WAITING_EVENT_SEATS

    seats = int(seats_str)
    new_event = context.user_data["new_event"]

    # Генерируем уникальный ID
    events = context.bot_data["events"]
    event_id = f"event_{len(events) + 1}"

    # Добавляем в память
    events[event_id] = {
        "name": new_event["name"],
        "datetime_str": new_event["datetime_str"],
        "desc": new_event["desc"],
        "max_seats": seats,
        "registered_users": {}
    }

    # Сохраняем в Excel
    new_row = pd.DataFrame([{
        "event_id": event_id,
        "name": new_event["name"],
        "datetime_str": new_event["datetime_str"],
        "desc": new_event["desc"],
        "max_seats": seats
    }])

    try:
        df = pd.read_excel(EVENTS_FILE)
        df = pd.concat([df, new_row], ignore_index=True)
        df.to_excel(EVENTS_FILE, index=False)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка сохранения: {e}")
        return ConversationHandler.END

    await update.message.reply_text(
        f"✅ Мероприятие добавлено!\n\n"
        f"📌 {new_event['name']}\n"
        f"📅 {new_event['datetime_str']}\n"
        f"👥 Максимум: {seats} человек\n"
        f"📝 {new_event['desc']}"
    )

    # Вернуть в админ-панель
    await show_admin_panel(update, context)
    return ConversationHandler.END

# --- УДАЛЕНИЕ МЕРОПРИЯТИЯ ---
async def start_delete_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if update.effective_user.id != ADMIN_ID:
        await query.edit_message_text("⛔ Нет доступа.")
        return

    events = context.bot_data["events"]
    if not events:
        await query.edit_message_text("📭 Нет мероприятий для удаления.", reply_markup=get_admin_menu())
        return

    keyboard = []
    for event_id, event in events.items():
        btn_text = f"{event['name']} ({event['datetime_str']})"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"delete_confirm_{event_id}")])
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="admin_back")])

    await query.edit_message_text("⚠️ Выберите мероприятие для удаления:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

async def confirm_delete_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    event_id = "_".join(query.data.split("_")[2:])  # delete_confirm_event_1 → event_1
    events = context.bot_data["events"]

    if event_id not in events:
        await query.edit_message_text("❌ Мероприятие не найдено.")
        return

    event = events[event_id]

    # Удаляем из Excel
    try:
        df_events = pd.read_excel(EVENTS_FILE)
        df_events = df_events[df_events["event_id"] != event_id]
        df_events.to_excel(EVENTS_FILE, index=False)

        # Удаляем регистрации
        df_reg = pd.read_excel(REGISTRATIONS_FILE)
        df_reg = df_reg[df_reg["event_id"] != event_id]
        df_reg.to_excel(REGISTRATIONS_FILE, index=False)
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка при удалении: {e}")
        return

    # Удаляем из памяти
    del events[event_id]

    await query.edit_message_text(f"🗑 Мероприятие '{event['name']}' удалено.")
    await show_admin_panel(query, context)

# --- МЕРОПРИЯТИЯ ---
async def show_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    events = context.bot_data["events"]
    active_events = {k: v for k, v in events.items() if is_event_active(v)}

    if not active_events:
        await query.edit_message_text(
            "📭 К сожалению, нет доступных мероприятий.\nВсе события уже прошли.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="back")]])
        )
        return

    keyboard = []
    for event_id, event in active_events.items():
        free = event["max_seats"] - len(event["registered_users"])
        btn_text = f"{event['name']} ({free} мест)"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"select_{event_id}")])
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back")])

    await query.edit_message_text("Выберите мероприятие:", reply_markup=InlineKeyboardMarkup(keyboard))

# --- РЕГИСТРАЦИЯ НА МЕРОПРИЯТИЕ ---
async def select_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Извлекаем event_id из callback_data: например, "select_event_1" → event_1
    data_parts = query.data.split("_", 2)

    if len(data_parts) < 2:
        await query.edit_message_text("❌ Ошибка: неверные данные.")
        return ConversationHandler.END

    event_id = "_".join(data_parts[1:])  # собираем обратно, если было "select_event_1"

    events = context.bot_data["events"]

    if event_id not in events:
        await query.edit_message_text("❌ Мероприятие не найдено.")
        return ConversationHandler.END

    event = events[event_id]

    # Проверяем, активно ли мероприятие
    if not is_event_active(event):
        await query.edit_message_text("📅 Это мероприятие уже прошло.")
        return ConversationHandler.END

    user_id = update.effective_user.id

    # Проверяем, уже ли зарегистрирован
    if user_id in event["registered_users"]:
        await query.edit_message_text(
            "✅ Вы уже зарегистрированы на это мероприятие.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="events")]])
        )
        return ConversationHandler.END

    # Проверяем, есть ли места
    if len(event["registered_users"]) >= event["max_seats"]:
        await query.edit_message_text(
            "🚫 Все места заняты.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="events")]])
        )
        return ConversationHandler.END

    # Сохраняем выбранное событие
    context.user_data["selected_event_id"] = event_id

    # Запрашиваем ФИО
    await query.edit_message_text("📝 Пожалуйста, введите ваше полное имя (ФИО):")
    return INPUT_NAME

# --- Ввод ФИО ---
async def input_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if len(name) < 3:
        await update.message.reply_text("❗ Пожалуйста, введите корректное ФИО:")
        return INPUT_NAME
    context.user_data["name"] = name
    await update.message.reply_text("📧 Теперь введите ваш email:")
    return INPUT_EMAIL

def is_valid_email(email):
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None

# --- Ввод email ---
async def input_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = update.message.text.strip()

    # Проверяем email
    if not is_valid_email(email):
        await update.message.reply_text(
            "❌ Некорректный email. Пожалуйста, введите действительный адрес (например, user@example.com):"
        )
        return INPUT_EMAIL  # возвращаемся к вводу email

    user_id = update.effective_user.id
    event_id = context.user_data["selected_event_id"]
    events = context.bot_data["events"]
    event = events[event_id]

    # Сохраняем регистрацию
    save_registration(user_id, context.user_data["name"], email, event_id, event["name"])
    event["registered_users"][user_id] = {
        "name": context.user_data["name"],
        "email": email
    }

    # Отправляем подтверждение
    await update.message.reply_text(
        f"🎉 Поздравляем, {context.user_data['name']}!\n\n"
        f"Вы успешно зарегистрированы на:\n\n"
        f"📌 {event['name']}\n"
        f"📅 {event['datetime_str']}\n"
        f"📧 На ваш email {email} отправлено подтверждение.\n\n"
        f"Ждём вас с нетерпением! 😊",
        reply_markup=get_main_menu()
    )
    return ConversationHandler.END

async def start_remind_unconfirmed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if update.effective_user.id != ADMIN_ID:
        await query.edit_message_text("⛔ Нет доступа.")
        return

    events = context.bot_data["events"]

    if not events:
        await query.edit_message_text("ostringstream Нет мероприятий.", reply_markup=get_admin_menu())
        return

    keyboard = []
    for event_id, event in events.items():
        reg_count = len(event["registered_users"])
        if reg_count > 0:
            # Считаем, сколько не подтвердило
            not_confirmed_count = 0
            for user_id, user_data in event["registered_users"].items():
                if user_data.get("status") != "confirmed":
                    not_confirmed_count += 1

            btn_text = f"{event['name']} (нужно: {not_confirmed_count})"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"remind_event_{event_id}")])
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="admin_back")])

    await query.edit_message_text(
        "Выберите мероприятие, участникам которого нужно напомнить о подтверждении:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def send_remind_unconfirmed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if update.effective_user.id != ADMIN_ID:
        await query.edit_message_text("⛔ Нет доступа.")
        return

    event_id = "_".join(query.data.split("_")[2:])
    events = context.bot_data["events"]

    if event_id not in events:
        await query.edit_message_text("❌ Мероприятие не найдено.", reply_markup=get_admin_menu())
        return

    event = events[event_id]

    try:
        df = pd.read_excel(REGISTRATIONS_FILE)
        # Фильтр: это мероприятие + статус НЕ "confirmed"
        df_filtered = df[(df["event_id"] == event_id) & (df["status"] != "confirmed")]
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка загрузки данных: {e}")
        return

    if df_filtered.empty:
        await query.edit_message_text(
            f"✅ Все участники мероприятия *{event['name']}* уже подтвердили участие!",
            parse_mode="Markdown",
            reply_markup=get_admin_menu()
        )
        return

    # Текст напоминания
    message_text = (
        f"⏰ *Напоминание*\n\n"
        f"До мероприятия **{event['name']}** осталось немного времени!\n\n"
        f"Пожалуйста, подтвердите ваше участие, чтобы мы могли всё подготовить."
    )

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Подтвердить участие", callback_data=f"confirm_attendance_{event_id}")
    ]])

    sent_count = 0
    error_count = 0

    for _, row in df_filtered.iterrows():
        user_id = int(row["user_id"])
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=message_text,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            sent_count += 1
        except Exception as e:
            print(f"Ошибка при отправке {user_id}: {e}")
            error_count += 1
        await asyncio.sleep(0.05)  # Защита от лимитов

    await query.edit_message_text(
        f"✅ Напоминание отправлено!\n\n"
        f"📬 Участникам: *{event['name']}*\n"
        f"📤 Доставлено: {sent_count}\n"
        f"❌ Не удалось: {error_count}",
        parse_mode="Markdown",
        reply_markup=get_admin_menu()
    )
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Нет доступа.")
        return

    events = context.bot_data["events"]

    if not events:
        await update.message.reply_text("ostringstream Нет мероприятий.")
        return

    total_reg = 0
    total_confirmed = 0
    total_not_confirmed = 0

    details = []
    for event_id, event in events.items():
        reg_count = len(event["registered_users"])
        confirmed_count = 0
        for user_id, user_data in event["registered_users"].items():
            if user_data.get("status") == "confirmed":
                confirmed_count += 1
        not_confirmed = reg_count - confirmed_count

        total_reg += reg_count
        total_confirmed += confirmed_count
        total_not_confirmed += not_confirmed

        details.append(f"• {event['name']}: {reg_count} (✅ {confirmed_count}, ❌ {not_confirmed})")

    text = (
        f"📊 **Общая статистика**\n\n"
        f"Всего зарегистрировано: {total_reg}\n"
        f"Подтвердили: ✅ {total_confirmed}\n"
        f"Не подтвердили: ❌ {total_not_confirmed}\n\n"
        f"По мероприятиям:\n" + "\n".join(details)
    )

    await update.message.reply_text(text, parse_mode="Markdown")

# --- on_startup ---
async def on_startup(app: Application):
    init_files()
    load_bot_users()
    app.bot_data["events"] = load_registrations()
    print(f"✅ Бот запущен. Пользователей: {len(all_bot_users)}")

async def go_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Главное меню:", reply_markup=get_main_menu())

# --- main ---
def main():
    application = Application.builder().token(TOKEN).post_init(on_startup).build()

    # --- Конверсации ---
    reg_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(select_event, pattern=r"^select_.*$")],
        states={
            INPUT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_name)],
            INPUT_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_email)],
        },
        fallbacks=[CommandHandler("start", start)],
        per_user=True
    )

    admin_conv = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_command)],
        states={
            WAITING_ADMIN_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_password)]
        },
        fallbacks=[CommandHandler("start", start)],
        per_user=True
    )

    broadcast_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_broadcast, pattern="^broadcast$")],
        states={
            WAITING_BROADCAST_MESSAGE: [MessageHandler(filters.PHOTO | filters.TEXT, receive_broadcast_message)],
            WAITING_BROADCAST_CONFIRM: [
                CallbackQueryHandler(confirm_broadcast, pattern="^confirm_broadcast$"),
                CallbackQueryHandler(cancel_broadcast, pattern="^cancel_broadcast$")
            ]
        },
        fallbacks=[CommandHandler("start", start)],
        per_user=True
    )

    add_event_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add_event, pattern="^add_event$")],
        states={
            WAITING_EVENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_event_name)],
            WAITING_EVENT_DATETIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_event_datetime)],
            WAITING_EVENT_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_event_desc)],
            WAITING_EVENT_SEATS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_event_seats)],
        },
        fallbacks=[CommandHandler("cancel", start)],
        per_user=True
    )

    # --- Регистрация обработчиков ---
    application.add_handler(CommandHandler("start", start))
    application.add_handler(reg_conv)
    application.add_handler(admin_conv)
    application.add_handler(broadcast_conv)
    application.add_handler(add_event_conv)

    # --- Кнопки ---
    application.add_handler(CallbackQueryHandler(show_events, pattern="^events$"))
    application.add_handler(CallbackQueryHandler(go_back, pattern="^back$"))
    # --- Информация ---
    application.add_handler(CallbackQueryHandler(info_handler, pattern="^links$"))
    application.add_handler(CallbackQueryHandler(info_handler, pattern="^podcasts$"))
    application.add_handler(CallbackQueryHandler(info_handler, pattern="^knowledge_base$"))
    application.add_handler(CallbackQueryHandler(info_handler, pattern="^educational_orgs$"))
    application.add_handler(CallbackQueryHandler(info_handler, pattern="^tips_deaf$"))
    application.add_handler(CallbackQueryHandler(info_handler, pattern="^tips_intro$"))
    application.add_handler(CallbackQueryHandler(info_handler, pattern="^internship$"))

    # --- Назад/Подтверждение ---
    application.add_handler(CallbackQueryHandler(back_to_menu, pattern="^back_to_menu$"))
    application.add_handler(CallbackQueryHandler(confirm_participation, pattern=r"^confirm_attendance_.*$"))

    # Обработчик напоминания о подтверждении
    application.add_handler(CallbackQueryHandler(start_remind_unconfirmed, pattern="^remind_unconfirmed$"))
    application.add_handler(CallbackQueryHandler(send_remind_unconfirmed, pattern=r"^remind_event_.*$"))
    # --- Админ ---
    application.add_handler(CallbackQueryHandler(show_admin_panel, pattern="^admin_panel$"))
    application.add_handler(CallbackQueryHandler(export_all, pattern="^export_all$"))
    application.add_handler(CallbackQueryHandler(export_all_users, pattern="^export_all_users$"))
    application.add_handler(CallbackQueryHandler(start_delete_event, pattern="^delete_event$"))
    application.add_handler(CallbackQueryHandler(confirm_delete_event, pattern=r"^delete_confirm_.*$"))
    application.add_handler(CommandHandler("stats", show_stats))
    print("🚀 Бот запущен. Напишите /start")
    application.run_polling()

if __name__ == "__main__":
    main()