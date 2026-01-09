from __future__ import annotations

from typing import Optional, List

from ...constants import Role
from ..db import Database


class RoleRepository:
    def __init__(self, db: Database):
        self.db = db

    async def get_role(self, user_id: int) -> Role:
        row = await self.db.fetchone(
            "SELECT role FROM roles WHERE user_id = ?", (user_id,)
        )
        if not row:
            return Role.USER
        try:
            return Role(row["role"])
        except ValueError:
            return Role.USER

    async def set_role(self, user_id: int, role: Role):
        await self.db.execute(
            """
            INSERT INTO roles (user_id, role)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET role = excluded.role
            """,
            (user_id, role.value),
        )

    async def list_roles(self) -> List[tuple[int, Role]]:
        rows = await self.db.fetchall("SELECT user_id, role FROM roles")
        return [(row["user_id"], Role(row["role"])) for row in rows]

