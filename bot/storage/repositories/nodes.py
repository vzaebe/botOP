from __future__ import annotations

from typing import List, Optional

from ...models import Node
from ..db import Database


class NodeRepository:
    def __init__(self, db: Database):
        self.db = db

    async def get_node(self, node_id: int) -> Optional[Node]:
        row = await self.db.fetchone(
            "SELECT id, parent_id, key, title, content, url, order_index, is_main_menu FROM nodes WHERE id = ?",
            (node_id,),
        )
        if not row:
            return None
        return Node(
            id=row["id"],
            parent_id=row["parent_id"],
            key=row["key"],
            title=row["title"],
            content=row["content"],
            url=row["url"],
            order_index=row["order_index"],
            is_main_menu=bool(row["is_main_menu"]),
        )

    async def get_node_by_key(self, key: str) -> Optional[Node]:
        row = await self.db.fetchone(
            "SELECT id, parent_id, key, title, content, url, order_index, is_main_menu FROM nodes WHERE key = ?",
            (key,),
        )
        if not row:
            return None
        return Node(
            id=row["id"],
            parent_id=row["parent_id"],
            key=row["key"],
            title=row["title"],
            content=row["content"],
            url=row["url"],
            order_index=row["order_index"],
            is_main_menu=bool(row["is_main_menu"]),
        )

    async def get_children(self, parent_id: Optional[int]) -> List[Node]:
        if parent_id is None:
            rows = await self.db.fetchall(
                "SELECT id, parent_id, key, title, content, url, order_index, is_main_menu FROM nodes WHERE parent_id IS NULL ORDER BY order_index"
            )
        else:
            rows = await self.db.fetchall(
                "SELECT id, parent_id, key, title, content, url, order_index, is_main_menu FROM nodes WHERE parent_id = ? ORDER BY order_index",
                (parent_id,),
            )
        return [
            Node(
                id=row["id"],
                parent_id=row["parent_id"],
                key=row["key"],
                title=row["title"],
                content=row["content"],
                url=row["url"],
                order_index=row["order_index"],
                is_main_menu=bool(row["is_main_menu"]),
            )
            for row in rows
        ]

    async def upsert_node(self, node: Node) -> int:
        if node.id is not None:
            await self.db.execute(
                """
                UPDATE nodes SET parent_id = ?, key = ?, title = ?, content = ?, url = ?, order_index = ?, is_main_menu = ?
                WHERE id = ?
                """,
                (
                    node.parent_id,
                    node.key,
                    node.title,
                    node.content,
                    node.url,
                    node.order_index,
                    1 if node.is_main_menu else 0,
                    node.id,
                ),
            )
            return node.id
        else:
            conn = await self.db.connect()
            cursor = await conn.execute(
                """
                INSERT INTO nodes (parent_id, key, title, content, url, order_index, is_main_menu)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    node.parent_id,
                    node.key,
                    node.title,
                    node.content,
                    node.url,
                    node.order_index,
                    1 if node.is_main_menu else 0,
                ),
            )
            node_id = cursor.lastrowid
            await conn.commit()
            return node_id

    async def list_all_nodes(self) -> List[Node]:
        rows = await self.db.fetchall(
            "SELECT id, parent_id, key, title, content, url, order_index, is_main_menu FROM nodes ORDER BY parent_id, order_index"
        )
        return [
            Node(
                id=row["id"],
                parent_id=row["parent_id"],
                key=row["key"],
                title=row["title"],
                content=row["content"],
                url=row["url"],
                order_index=row["order_index"],
                is_main_menu=bool(row["is_main_menu"]),
            )
            for row in rows
        ]

    async def get_main_menu_nodes(self) -> List[Node]:
        rows = await self.db.fetchall(
            "SELECT id, parent_id, key, title, content, url, order_index, is_main_menu FROM nodes WHERE is_main_menu = 1 ORDER BY order_index"
        )
        return [
            Node(
                id=row["id"],
                parent_id=row["parent_id"],
                key=row["key"],
                title=row["title"],
                content=row["content"],
                url=row["url"],
                order_index=row["order_index"],
                is_main_menu=bool(row["is_main_menu"]),
            )
            for row in rows
        ]

    async def delete_node(self, node_id: int):
        await self.db.execute("DELETE FROM nodes WHERE id = ?", (node_id,))
