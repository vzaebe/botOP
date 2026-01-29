from __future__ import annotations

from typing import List, Optional

from ..logging_config import logger
from ..models import Node


class NodeService:
    def __init__(self, repo):
        self.repo = repo

    async def get_node(self, node_id: int) -> Optional[Node]:
        return await self.repo.get_node(node_id)

    async def get_node_by_key(self, key: str) -> Optional[Node]:
        return await self.repo.get_node_by_key(key)

    async def get_children(self, parent_id: Optional[int]) -> List[Node]:
        return await self.repo.get_children(parent_id)

    async def save_node(
        self,
        title: str,
        content: str,
        parent_id: Optional[int] = None,
        key: Optional[str] = None,
        url: Optional[str] = None,
        order_index: int = 0,
        is_main_menu: bool = False,
        node_id: Optional[int] = None,
    ) -> int:
        node = Node(
            id=node_id,
            parent_id=parent_id,
            key=key,
            title=title,
            content=content,
            url=url,
            order_index=order_index,
            is_main_menu=is_main_menu,
        )
        node_id = await self.repo.upsert_node(node)
        logger and logger.debug("Saved node id=%s key=%s parent=%s", node_id, key, parent_id)
        return node_id

    async def delete_node(self, node_id: int):
        await self.repo.delete_node(node_id)
        logger and logger.info("Deleted node id=%s", node_id)

    async def get_all_nodes(self) -> List[Node]:
        return await self.repo.list_all_nodes()

    async def get_main_menu_nodes(self) -> List[Node]:
        return await self.repo.get_main_menu_nodes()

    async def ensure_defaults(self):
        nodes = await self.get_all_nodes()
        if nodes:
            return

        info_id = await self.save_node(
            title="ℹ️ Информация",
            content="Быстрые ссылки по разделам:",
            key="info",
            order_index=3,
            is_main_menu=True,
        )
        await self.save_node(
            parent_id=info_id,
            title="Полезные ссылки",
            content="Список ссылок:",
            key="links",
            order_index=1,
        )
        await self.save_node(
            parent_id=info_id,
            title="Подкасты",
            content="Свежие выпуски и интервью:",
            key="podcasts",
            order_index=2,
        )
        logger and logger.info("Default nodes created")
