from __future__ import annotations

import logging
import time

from telegram.ext import Application, ApplicationBuilder

from .config import load_config
from .constants import Role
from .handlers import admin as admin_handlers
from .handlers import content as content_handlers
from .handlers import events as events_handlers
from .handlers import menu as menu_handlers
from .handlers import profile as profile_handlers
from .handlers import start as start_handlers
from .logging_config import setup_logging
from .services.content import ContentService
from .services.events import EventService
from .services.migrations import MigrationService
from .services.nodes import NodeService
from .services.profiles import ProfileService
from .services.restart import RestartService
from .storage.db import Database
from .storage.repositories.content import ContentRepository
from .storage.repositories.events import EventRepository
from .storage.repositories.nodes import NodeRepository
from .storage.repositories.registrations import RegistrationRepository
from .storage.repositories.roles import RoleRepository
from .storage.repositories.users import UserRepository
from .utils.errors import PermissionDenied

logger = logging.getLogger(__name__)


async def on_startup(app: Application):
    logger.info("Bootstrapping bot...")
    app.bot_data.setdefault("started_at", time.time())
    config = app.bot_data["config"]
    db: Database = app.bot_data["db"]

    try:
        await db.init_db()
        logger.info("Database initialized at %s", db.path)
    except Exception:
        logger.exception("Failed to initialize database")
        raise

    migrator: MigrationService = app.bot_data["migrator"]
    try:
        await migrator.migrate_from_files()
    except Exception:
        logger.exception("Migration failed; continuing without legacy import")

    content_service: ContentService = app.bot_data["content_service"]
    node_service: NodeService = app.bot_data["node_service"]
    try:
        await content_service.ensure_defaults()
        await node_service.ensure_defaults()
    except Exception:
        logger.exception("Failed to ensure default content or nodes")

    profile_service = app.bot_data["profile_service"]
    for admin_id in config.admin_ids:
        await profile_service.ensure_user(admin_id, username="", full_name=f"admin-{admin_id}")
        await profile_service.assign_role(admin_id, Role.ADMIN)
        logger.info("Granted admin role from config to user_id=%s", admin_id)


async def on_shutdown(app: Application):
    db: Database = app.bot_data.get("db")
    if db:
        await db.close()
        logger.info("Database connection closed")
    logger.info("Bot shutdown complete")


async def on_error(update, context):
    err = context.error
    chat_id = getattr(getattr(update, "effective_chat", None), "id", None)
    logger.exception("Handler error (chat_id=%s): %s", chat_id, err)
    if update and update.effective_message:
        try:
            if isinstance(err, PermissionDenied):
                await update.effective_message.reply_text("⛔ Недостаточно прав для этой команды.")
            else:
                await update.effective_message.reply_text(
                    "⚠️ Что-то пошло не так. Я уже записал ошибку в лог и попробую работать дальше."
                )
        except Exception:
            logger.exception("Failed to send error message to chat_id=%s", chat_id)


def build_application() -> Application:
    config = load_config()
    setup_logging(
        config.log_level,
        log_file=config.log_file,
        max_bytes=config.log_max_bytes,
        backup_count=config.log_backup_count,
    )
    started_at = time.time()
    db = Database(config.database_path)
    user_repo = UserRepository(db)
    role_repo = RoleRepository(db)
    event_repo = EventRepository(db)
    reg_repo = RegistrationRepository(db)
    content_repo = ContentRepository(db)
    node_repo = NodeRepository(db)

    profile_service = ProfileService(user_repo, role_repo)
    event_service = EventService(event_repo, reg_repo)
    content_service = ContentService(content_repo)
    node_service = NodeService(node_repo)
    migrator = MigrationService(user_repo, role_repo, event_repo, reg_repo, content_repo)

    app = (
        ApplicationBuilder()
        .token(config.bot_token)
        .post_init(on_startup)
        .post_shutdown(on_shutdown)
        .build()
    )

    app.bot_data["config"] = config
    app.bot_data["db"] = db
    app.bot_data["profile_service"] = profile_service
    app.bot_data["event_service"] = event_service
    app.bot_data["content_service"] = content_service
    app.bot_data["node_service"] = node_service
    app.bot_data["migrator"] = migrator
    app.bot_data["role_service"] = profile_service  # reuse profile service for role ops
    app.bot_data["restart_service"] = RestartService(
        enabled=config.restart_enabled,
        exit_code=config.restart_exit_code,
    )
    app.bot_data["started_at"] = started_at

    start_handlers.setup_handlers(app)
    profile_handlers.setup_handlers(app)
    events_handlers.setup_handlers(app)
    admin_handlers.setup_handlers(app)
    content_handlers.setup_handlers(app)
    menu_handlers.setup_handlers(app)
    app.add_error_handler(on_error)
    logger.info(
        "Bot initialized (log_level=%s, db=%s, admins=%s, restart_enabled=%s)",
        config.log_level,
        config.database_path,
        len(config.admin_ids),
        config.restart_enabled,
    )
    return app


def main():
    application = build_application()
    logger.info("Starting polling...")
    application.run_polling()


if __name__ == "__main__":
    main()
