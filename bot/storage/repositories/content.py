from __future__ import annotations

from typing import List, Optional

from ...models import ContentSection, MenuItem, Template
from ..db import Database


class ContentRepository:
    def __init__(self, db: Database):
        self.db = db

    async def list_sections(self) -> List[ContentSection]:
        rows = await self.db.fetchall(
            "SELECT key, title, body FROM content_sections ORDER BY key"
        )
        return [ContentSection(row["key"], row["title"], row["body"]) for row in rows]

    async def get_section(self, key: str) -> Optional[ContentSection]:
        row = await self.db.fetchone(
            "SELECT key, title, body FROM content_sections WHERE key = ?", (key,)
        )
        if not row:
            return None
        return ContentSection(row["key"], row["title"], row["body"])

    async def upsert_section(self, section: ContentSection):
        await self.db.execute(
            """
            INSERT INTO content_sections (key, title, body)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET title = excluded.title, body = excluded.body
            """,
            (section.key, section.title, section.body),
        )

    async def delete_section(self, key: str):
        await self.db.execute("DELETE FROM content_sections WHERE key = ?", (key,))

    async def list_menu_items(self) -> List[MenuItem]:
        rows = await self.db.fetchall(
            "SELECT key, title, position FROM menu_items ORDER BY position"
        )
        return [MenuItem(row["key"], row["title"], row["position"]) for row in rows]

    async def upsert_menu_item(self, item: MenuItem):
        await self.db.execute(
            """
            INSERT INTO menu_items (key, title, position)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET title = excluded.title, position = excluded.position
            """,
            (item.key, item.title, item.position),
        )

    async def delete_menu_item(self, key: str):
        await self.db.execute("DELETE FROM menu_items WHERE key = ?", (key,))

    async def list_templates(self) -> List[Template]:
        rows = await self.db.fetchall("SELECT key, body FROM templates")
        return [Template(row["key"], row["body"]) for row in rows]

    async def get_template(self, key: str) -> Optional[Template]:
        row = await self.db.fetchone("SELECT key, body FROM templates WHERE key = ?", (key,))
        if not row:
            return None
        return Template(row["key"], row["body"])

    async def upsert_template(self, template: Template):
        await self.db.execute(
            """
            INSERT INTO templates (key, body)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET body = excluded.body
            """,
            (template.key, template.body),
        )

