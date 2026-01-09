from __future__ import annotations

from typing import Optional, List

from ...models import User, utcnow_str
from ...constants import Role
from ..db import Database


class UserRepository:
    def __init__(self, db: Database):
        self.db = db

    async def upsert_user(
        self, user_id: int, username: str, full_name: str
    ) -> User:
        existing = await self.get_user(user_id)
        if existing:
            await self.db.execute(
                """
                UPDATE users
                   SET username = ?, full_name = ?, updated_at = ?
                 WHERE user_id = ?
                """,
                (username, full_name, utcnow_str(), user_id),
            )
            return await self.get_user(user_id)  # type: ignore
        await self.db.execute(
            """
            INSERT INTO users (user_id, username, full_name, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, username, full_name, utcnow_str(), utcnow_str()),
        )
        await self.db.execute(
            """
            INSERT OR IGNORE INTO roles (user_id, role)
            VALUES (?, ?)
            """,
            (user_id, Role.USER.value),
        )
        return await self.get_user(user_id)  # type: ignore

    async def get_user(self, user_id: int) -> Optional[User]:
        row = await self.db.fetchone(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        )
        if not row:
            return None
        return User(
            user_id=row["user_id"],
            username=row["username"] or "",
            full_name=row["full_name"] or "",
            email=row["email"] or "",
            consent=bool(row["consent"]),
            consent_time=row["consent_time"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def update_profile(
        self, user_id: int, full_name: Optional[str], email: Optional[str]
    ) -> Optional[User]:
        user = await self.get_user(user_id)
        if not user:
            return None
        new_name = full_name if full_name is not None else user.full_name
        new_email = email if email is not None else user.email
        await self.db.execute(
            """
            UPDATE users
               SET full_name = ?, email = ?, updated_at = ?
             WHERE user_id = ?
            """,
            (new_name, new_email, utcnow_str(), user_id),
        )
        return await self.get_user(user_id)

    async def set_email(self, user_id: int, email: str):
        await self.db.execute(
            "UPDATE users SET email = ?, updated_at = ? WHERE user_id = ?",
            (email, utcnow_str(), user_id),
        )

    async def set_full_name(self, user_id: int, full_name: str):
        await self.db.execute(
            "UPDATE users SET full_name = ?, updated_at = ? WHERE user_id = ?",
            (full_name, utcnow_str(), user_id),
        )

    async def set_consent(self, user_id: int, consent: bool):
        await self.db.execute(
            "UPDATE users SET consent = ?, consent_time = ?, updated_at = ? WHERE user_id = ?",
            (1 if consent else 0, utcnow_str(), utcnow_str(), user_id),
        )

    async def list_users(self) -> List[User]:
        rows = await self.db.fetchall("SELECT * FROM users")
        return [
            User(
                user_id=row["user_id"],
                username=row["username"] or "",
                full_name=row["full_name"] or "",
                email=row["email"] or "",
                consent=bool(row["consent"]),
                consent_time=row["consent_time"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

