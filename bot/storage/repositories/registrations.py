from __future__ import annotations

from typing import List, Optional

from ...models import Registration
from ..db import Database


class RegistrationRepository:
    def __init__(self, db: Database):
        self.db = db

    async def list_by_event(self, event_id: str) -> List[Registration]:
        rows = await self.db.fetchall(
            "SELECT * FROM registrations WHERE event_id = ?", (event_id,)
        )
        return [
            Registration(
                id=row["id"],
                user_id=row["user_id"],
                event_id=row["event_id"],
                status=row["status"],
                reg_time=row["reg_time"],
            )
            for row in rows
        ]

    async def list_by_user(self, user_id: int) -> List[Registration]:
        rows = await self.db.fetchall(
            "SELECT * FROM registrations WHERE user_id = ?", (user_id,)
        )
        return [
            Registration(
                id=row["id"],
                user_id=row["user_id"],
                event_id=row["event_id"],
                status=row["status"],
                reg_time=row["reg_time"],
            )
            for row in rows
        ]

    async def get(self, user_id: int, event_id: str) -> Optional[Registration]:
        row = await self.db.fetchone(
            "SELECT * FROM registrations WHERE user_id = ? AND event_id = ?",
            (user_id, event_id),
        )
        if not row:
            return None
        return Registration(
            id=row["id"],
            user_id=row["user_id"],
            event_id=row["event_id"],
            status=row["status"],
            reg_time=row["reg_time"],
        )

    async def create(self, registration: Registration) -> int:
        await self.db.execute(
            """
            INSERT INTO registrations (user_id, event_id, status, reg_time)
            VALUES (?, ?, ?, ?)
            """,
            (
                registration.user_id,
                registration.event_id,
                registration.status,
                registration.reg_time,
            ),
        )
        row = await self.db.fetchone("SELECT last_insert_rowid() AS id")
        return int(row["id"]) if row else 0

    async def update_status(self, reg_id: int, status: str):
        await self.db.execute(
            "UPDATE registrations SET status = ? WHERE id = ?", (status, reg_id)
        )

    async def delete_by_event(self, event_id: str):
        await self.db.execute(
            "DELETE FROM registrations WHERE event_id = ?", (event_id,)
        )

