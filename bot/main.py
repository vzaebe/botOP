from __future__ import annotations
from telegram.ext import Application, ApplicationBuilder, MessageHandler, filters

from .config import load_config
from .logging_config import setup_logging
from .storage.db import Database
from .storage.repositories.users import UserRepository
from .storage.repositories.roles import RoleRepository
from .storage.repositories.events import EventRepository
from .storage.repositories.registrations import RegistrationRepository
from .storage.repositories.content import ContentRepository
from .services.profiles import ProfileService
from .services.events import EventService
from .services.content import ContentService
from .constants import Role
from .services.migrations import MigrationService
from .services.restart import RestartService
from .handlers import start as start_handlers
from .handlers import profile as profile_handlers
from .handlers import events as events_handlers
from .handlers import admin as admin_handlers
from .handlers import content as content_handlers
from .services.messaging import send_main_menu
from .utils.errors import PermissionDenied
import logging


async def on_startup(app: Application):
    config = app.bot_data["config"]
    db: Database = app.bot_data["db"]
    await db.init_db()
    # migrate
    migrator: MigrationService = app.bot_data["migrator"]
    await migrator.migrate_from_files()
    content_service: ContentService = app.bot_data["content_service"]
    await content_service.ensure_defaults()
    app.bot_data["restart_service"] = RestartService(enabled=True)
    # grant admin roles from config
    profile_service = app.bot_data["profile_service"]
    for admin_id in config.admin_ids:
        await profile_service.assign_role(admin_id, Role.ADMIN)


async def fallback_menu(update, context):
    await send_main_menu(context, update.effective_chat.id, text="Выберите действие:")


async def on_error(update, context):
    err = context.error
    logging.exception("Handler error: %s", err)
    if update and update.effective_message:
        if isinstance(err, PermissionDenied):
            await update.effective_message.reply_text("⛔ Нет доступа")
        else:
            await update.effective_message.reply_text("❌ Произошла ошибка. Попробуйте позже.")


def build_application() -> Application:
    config = load_config()
    logger = setup_logging(config.log_level)
    db = Database(config.database_path)
    user_repo = UserRepository(db)
    role_repo = RoleRepository(db)
    event_repo = EventRepository(db)
    reg_repo = RegistrationRepository(db)
    content_repo = ContentRepository(db)

    profile_service = ProfileService(user_repo, role_repo)
    event_service = EventService(event_repo, reg_repo)
    content_service = ContentService(content_repo)
    migrator = MigrationService(user_repo, role_repo, event_repo, reg_repo, content_repo)

    app = (
        ApplicationBuilder()
        .token(config.bot_token)
        .post_init(on_startup)
        .build()
    )

    app.bot_data["config"] = config
    app.bot_data["db"] = db
    app.bot_data["profile_service"] = profile_service
    app.bot_data["event_service"] = event_service
    app.bot_data["content_service"] = content_service
    app.bot_data["migrator"] = migrator
    app.bot_data["role_service"] = profile_service  # reuse profile service for role ops
    app.bot_data["restart_service"] = RestartService(enabled=True)

    start_handlers.setup_handlers(app)
    profile_handlers.setup_handlers(app)
    events_handlers.setup_handlers(app)
    admin_handlers.setup_handlers(app)
    content_handlers.setup_handlers(app)

    # Fallback to show menu for unknown text
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_menu))
    app.add_error_handler(on_error)
    logger.info("Bot initialized")
    return app


def main():
    application = build_application()
    application.run_polling()


if __name__ == "__main__":
    main()

