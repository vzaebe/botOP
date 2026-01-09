from __future__ import annotations

import os
from typing import Optional, Iterable, Any, Dict, List

import aiosqlite


class Database:
    def __init__(self, path: str):
        self.path = path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> aiosqlite.Connection:
        if self._conn is None:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            self._conn = await aiosqlite.connect(self.path)
            await self._conn.execute("PRAGMA foreign_keys = ON;")
            await self._conn.execute("PRAGMA journal_mode = WAL;")
            await self._conn.execute("PRAGMA synchronous = NORMAL;")
        return self._conn

    async def execute(self, query: str, params: Iterable[Any] | Dict[str, Any] = ()):
        conn = await self.connect()
        await conn.execute(query, params)
        await conn.commit()

    async def fetchone(
        self, query: str, params: Iterable[Any] | Dict[str, Any] = ()
    ) -> Optional[aiosqlite.Row]:
        conn = await self.connect()
        conn.row_factory = aiosqlite.Row
        async with conn.execute(query, params) as cursor:
            return await cursor.fetchone()

    async def fetchall(
        self, query: str, params: Iterable[Any] | Dict[str, Any] = ()
    ) -> List[aiosqlite.Row]:
        conn = await self.connect()
        conn.row_factory = aiosqlite.Row
        async with conn.execute(query, params) as cursor:
            return await cursor.fetchall()

    async def init_db(self):
        await self.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                email TEXT,
                consent INTEGER DEFAULT 0,
                consent_time TEXT,
                created_at TEXT,
                updated_at TEXT
            );
        """
        )
        await self.execute(
            """
            CREATE TABLE IF NOT EXISTS roles (
                user_id INTEGER PRIMARY KEY,
                role TEXT NOT NULL DEFAULT 'user',
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );
        """
        )
        await self.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                datetime_str TEXT NOT NULL,
                description TEXT,
                max_seats INTEGER NOT NULL
            );
        """
        )
        await self.execute(
            """
            CREATE TABLE IF NOT EXISTS registrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                event_id TEXT NOT NULL,
                status TEXT DEFAULT 'registered',
                reg_time TEXT,
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                FOREIGN KEY(event_id) REFERENCES events(event_id) ON DELETE CASCADE
            );
        """
        )
        await self.execute(
            """
            CREATE TABLE IF NOT EXISTS content_sections (
                key TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                body TEXT NOT NULL
            );
        """
        )
        await self.execute(
            """
            CREATE TABLE IF NOT EXISTS menu_items (
                key TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                position INTEGER NOT NULL
            );
        """
        )
        await self.execute(
            """
            CREATE TABLE IF NOT EXISTS templates (
                key TEXT PRIMARY KEY,
                body TEXT NOT NULL
            );
        """
        )
        await self.execute(
            """
            CREATE TABLE IF NOT EXISTS nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_id INTEGER,
                key TEXT UNIQUE,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                url TEXT,
                order_index INTEGER DEFAULT 0,
                is_main_menu INTEGER DEFAULT 0,
                FOREIGN KEY(parent_id) REFERENCES nodes(id) ON DELETE CASCADE
            );
        """
        )

