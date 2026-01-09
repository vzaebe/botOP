from __future__ import annotations

from typing import List, Optional

from ..models import ContentSection, MenuItem, Template
from ..logging_config import logger


DEFAULT_SECTIONS = {
    "links": ("🔗 Полезные ссылки", "Добавьте ссылки в админке"),
    "podcasts": ("🎧 Подкасты", "Добавьте подкасты в админке"),
}

DEFAULT_MENU = [
    ("events", "📋 Мероприятия", 1),
    ("profile", "👤 Профиль", 2),
    ("info", "ℹ️ Инфо", 3),
]

DEFAULT_TEMPLATES = {
    "registration_success": "🎉 Вы зарегистрированы на {event_name}\nДата: {event_datetime}",
    "reminder": "⏰ Напоминание о событии {event_name}",
}


class ContentService:
    def __init__(self, repo):
        self.repo = repo

    async def ensure_defaults(self):
        # populate sections if empty
        existing = await self.repo.list_sections()
        if not existing:
            for key, (title, body) in DEFAULT_SECTIONS.items():
                await self.repo.upsert_section(ContentSection(key=key, title=title, body=body))
        menu = await self.repo.list_menu_items()
        if not menu:
            for key, title, pos in DEFAULT_MENU:
                await self.repo.upsert_menu_item(MenuItem(key=key, title=title, position=pos))
        templates = await self.repo.list_templates()
        if not templates:
            for key, body in DEFAULT_TEMPLATES.items():
                await self.repo.upsert_template(Template(key=key, body=body))

    async def list_sections(self) -> List[ContentSection]:
        return await self.repo.list_sections()

    async def get_section(self, key: str) -> Optional[ContentSection]:
        return await self.repo.get_section(key)

    async def save_section(self, key: str, title: str, body: str):
        await self.repo.upsert_section(ContentSection(key=key, title=title, body=body))

    async def delete_section(self, key: str):
        await self.repo.delete_section(key)

    async def list_menu_items(self) -> List[MenuItem]:
        return await self.repo.list_menu_items()

    async def save_menu_item(self, key: str, title: str, position: int):
        await self.repo.upsert_menu_item(MenuItem(key=key, title=title, position=position))

    async def delete_menu_item(self, key: str):
        await self.repo.delete_menu_item(key)

    async def list_templates(self) -> List[Template]:
        return await self.repo.list_templates()

    async def get_template(self, key: str) -> Optional[Template]:
        return await self.repo.get_template(key)

    async def save_template(self, key: str, body: str):
        await self.repo.upsert_template(Template(key=key, body=body))

