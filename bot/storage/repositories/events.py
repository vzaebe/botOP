from __future__ import annotations

from typing import List, Optional

from ...models import Event
from ..db import Database


class EventRepository:
    def __init__(self, db: Database):
        self.db = db

    async def list_events(self) -> List[Event]:
        rows = await self.db.fetchall("SELECT * FROM events ORDER BY datetime_str ASC")
        return [
            Event(
                event_id=row["event_id"],
                name=row["name"],
                datetime_str=row["datetime_str"],
                description=row["description"],
                max_seats=row["max_seats"],
            )
            for row in rows
        ]

    async def get(self, event_id: str) -> Optional[Event]:
        row = await self.db.fetchone(
            "SELECT * FROM events WHERE event_id = ?", (event_id,)
        )
        if not row:
            return None
        return Event(
            event_id=row["event_id"],
            name=row["name"],
            datetime_str=row["datetime_str"],
            description=row["description"],
            max_seats=row["max_seats"],
        )

    async def add(self, event: Event):
        await self.db.execute(
            """
            INSERT INTO events (event_id, name, datetime_str, description, max_seats)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.name,
                event.datetime_str,
                event.description,
                event.max_seats,
            ),
        )

    async def update(self, event: Event):
        await self.db.execute(
            """
            UPDATE events
               SET name = ?, datetime_str = ?, description = ?, max_seats = ?
             WHERE event_id = ?
            """,
            (
                event.name,
                event.datetime_str,
                event.description,
                event.max_seats,
                event.event_id,
            ),
        )

    async def delete(self, event_id: str):
        await self.db.execute("DELETE FROM events WHERE event_id = ?", (event_id,))

