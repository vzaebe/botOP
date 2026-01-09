from __future__ import annotations

from typing import Optional

from ..models import User
from ..utils.validators import is_valid_email
from ..utils.errors import ValidationError
from ..logging_config import logger


class ProfileService:
    def __init__(self, user_repo, role_repo):
        self.user_repo = user_repo
        self.role_repo = role_repo

    async def ensure_user(self, user_id: int, username: str, full_name: str) -> User:
        return await self.user_repo.upsert_user(user_id, username, full_name)

    async def get_profile(self, user_id: int) -> Optional[User]:
        return await self.user_repo.get_user(user_id)

    async def update_email(self, user_id: int, email: str) -> User:
        if not is_valid_email(email):
            raise ValidationError("Некорректный email")
        await self.user_repo.set_email(user_id, email)
        return await self.user_repo.get_user(user_id)  # type: ignore

    async def update_full_name(self, user_id: int, full_name: str) -> User:
        if len(full_name.strip()) < 3:
            raise ValidationError("Имя слишком короткое")
        await self.user_repo.set_full_name(user_id, full_name.strip())
        return await self.user_repo.get_user(user_id)  # type: ignore

    async def set_consent(self, user_id: int, consent: bool):
        await self.user_repo.set_consent(user_id, consent)

    async def list_users(self):
        return await self.user_repo.list_users()

    async def assign_role(self, user_id: int, role):
        await self.role_repo.set_role(user_id, role)
        logger and logger.info("Role %s assigned to %s", role, user_id)

    async def get_role(self, user_id: int):
        return await self.role_repo.get_role(user_id)

