import asyncio
import logging
import os
import sys

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


class RestartService:
    def __init__(self, enabled: bool = True, exit_code: int = 1):
        self.enabled = enabled
        self.exit_code = exit_code

    async def schedule_restart(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        code: int | None = None,
    ):
        if not self.enabled:
            await update.effective_message.reply_text("Перезапуск отключен в настройках.")
            return
        await update.effective_message.reply_text("🔄 Перезапускаю бота, это займет пару секунд.")
        logger.info("Restart requested by user_id=%s", update.effective_user.id)
        await context.application.stop()
        await context.application.shutdown()
        db = context.application.bot_data.get("db")
        if db:
            await db.close()
        await asyncio.sleep(1)
        sys.stdout.flush()
        exit_code = self.exit_code if code is None else code
        os._exit(exit_code)

    async def reload_data(self, context: ContextTypes.DEFAULT_TYPE):
        logger.info("Reloading default content/nodes by admin request")
        await context.application.bot_data["content_service"].ensure_defaults()
        await context.application.bot_data["node_service"].ensure_defaults()
