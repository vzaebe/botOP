import asyncio
import os
import sys

from telegram import Update
from telegram.ext import ContextTypes


class RestartService:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    async def schedule_restart(self, update: Update, context: ContextTypes.DEFAULT_TYPE, code: int = 0):
        if not self.enabled:
            await update.effective_message.reply_text("Перезапуск отключен в конфигурации.")
            return
        await update.effective_message.reply_text("🔄 Перезапускаю бота... Процесс завершится, супервизор поднимет заново.")
        await context.application.stop()
        await context.application.shutdown()
        # Даем сообщению уйти
        await asyncio.sleep(1)
        sys.stdout.flush()
        os._exit(code)

    async def reload_data(self, context: ContextTypes.DEFAULT_TYPE):
        # Вся логика читает из БД по запросу, поэтому достаточно сбросить кэш контента
        await context.application.bot_data["content_service"].ensure_defaults()

