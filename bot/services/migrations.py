from __future__ import annotations

import json
import os
from datetime import datetime

from ..models import ContentSection, MenuItem, Template, Event, Registration, User
from ..logging_config import logger
from ..constants import Role


class MigrationService:
    def __init__(self, user_repo, role_repo, event_repo, reg_repo, content_repo):
        self.user_repo = user_repo
        self.role_repo = role_repo
        self.event_repo = event_repo
        self.reg_repo = reg_repo
        self.content_repo = content_repo

    def _migration_marker_path(self) -> str:
        # If legacy files are left in the folder, repeated Excel/JSON reads can slow down every restart.
        # User can delete this marker to force re-run migration.
        return os.path.join("data", ".legacy_migration_done")

    async def migrate_from_files(
        self,
        events_file: str = "events.xlsx",
        registrations_file: str = "registrations.xlsx",
        users_file: str = "bot_users.json",
    ):
        marker = self._migration_marker_path()
        if os.path.exists(marker):
            return

        if not (os.path.exists(events_file) or os.path.exists(registrations_file) or os.path.exists(users_file)):
            return

        # Heavy dependency: import lazily to keep bot startup fast on weak VPS.
        import pandas as pd

        logger and logger.info("Starting migration from legacy files...")

        # Users
        if os.path.exists(users_file):
            with open(users_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for uid_str, info in data.items():
                user_id = int(uid_str)
                user = User(
                    user_id=user_id,
                    username=info.get("username", ""),
                    full_name=info.get("name", ""),
                    email=info.get("email", ""),
                    consent=False,
                    consent_time=None,
                    created_at=info.get("first_seen"),
                    updated_at=info.get("first_seen"),
                )
                await self.user_repo.upsert_user(user.user_id, user.username, user.full_name)
                await self.user_repo.set_email(user.user_id, user.email)
                await self.role_repo.set_role(user.user_id, Role.USER)
            logger and logger.info("Users migrated: %s", len(data))

        # Events
        if os.path.exists(events_file):
            try:
                df_events = pd.read_excel(events_file)
                for _, row in df_events.iterrows():
                    event = Event(
                        event_id=str(row["event_id"]),
                        name=row["name"],
                        datetime_str=row["datetime_str"],
                        description=row["desc"],
                        max_seats=int(row["max_seats"]),
                    )
                    if not await self.event_repo.get(event.event_id):
                        await self.event_repo.add(event)
            except Exception as exc:
                logger and logger.error("Failed to migrate events: %s", exc)

        # Registrations
        if os.path.exists(registrations_file):
            try:
                df_reg = pd.read_excel(registrations_file)
                for _, row in df_reg.iterrows():
                    reg = Registration(
                        id=None,
                        user_id=int(row["user_id"]),
                        event_id=str(row["event_id"]),
                        status=row.get("status", "registered"),
                        reg_time=row.get("reg_time")
                        or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    )
                    existing = await self.reg_repo.get(reg.user_id, reg.event_id)
                    if not existing:
                        await self.reg_repo.create(reg)
            except Exception as exc:
                logger and logger.error("Failed to migrate registrations: %s", exc)

        await self.ensure_defaults()
        logger and logger.info("Migration done.")

        # Mark successful migration to avoid re-reading heavy legacy files on every restart.
        try:
            os.makedirs(os.path.dirname(marker), exist_ok=True)
            with open(marker, "w", encoding="utf-8") as f:
                f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        except Exception as exc:
            logger and logger.warning("Failed to write migration marker %s: %s", marker, exc)

    async def ensure_defaults(self):
        # fallback content
        existing = await self.content_repo.list_sections()
        if not existing:
            await self.content_repo.upsert_section(
                ContentSection(
                    key="knowledge_base",
                    title="📚 База знаний",
                    body="Добавьте текст в админке.",
                )
            )
        menu = await self.content_repo.list_menu_items()
        if not menu:
            await self.content_repo.upsert_menu_item(MenuItem(key="events", title="📋 Мероприятия", position=1))
            await self.content_repo.upsert_menu_item(MenuItem(key="profile", title="👤 Профиль", position=2))
            await self.content_repo.upsert_menu_item(MenuItem(key="info", title="ℹ️ Инфо", position=3))
        templates = await self.content_repo.list_templates()
        if not templates:
            await self.content_repo.upsert_template(
                Template(key="registration_success", body="🎉 Регистрация на {event_name}")
            )

