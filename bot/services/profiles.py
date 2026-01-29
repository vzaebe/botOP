from __future__ import annotations

from typing import Optional

from ..logging_config import logger
from ..models import User
from ..utils.errors import ValidationError
from ..utils.validators import is_valid_email


class ProfileService:
    def __init__(self, user_repo, role_repo):
        self.user_repo = user_repo
        self.role_repo = role_repo

    async def ensure_user(self, user_id: int, username: str, full_name: str) -> User:
        user = await self.user_repo.upsert_user(user_id, username, full_name)
        logger and logger.debug("Ensured user user_id=%s username=%s", user_id, username)
        return user

    async def get_profile(self, user_id: int) -> Optional[User]:
        return await self.user_repo.get_user(user_id)

    async def update_email(self, user_id: int, email: str) -> User:
        if not is_valid_email(email):
            raise ValidationError("Некорректный email. Укажите адрес вида name@example.com.")
        await self.user_repo.set_email(user_id, email)
        logger and logger.info("Email updated for user_id=%s", user_id)
        return await self.user_repo.get_user(user_id)  # type: ignore

    async def update_full_name(self, user_id: int, full_name: str) -> User:
        if len(full_name.strip()) < 3:
            raise ValidationError("Имя должно быть не короче 3 символов.")
        await self.user_repo.set_full_name(user_id, full_name.strip())
        logger and logger.info("Full name updated for user_id=%s", user_id)
        return await self.user_repo.get_user(user_id)  # type: ignore

    async def set_consent(self, user_id: int, consent: bool):
        await self.user_repo.set_consent(user_id, consent)
        logger and logger.info("Consent=%s saved for user_id=%s", consent, user_id)

    async def list_users(self):
        return await self.user_repo.list_users()

    async def assign_role(self, user_id: int, role):
        await self.role_repo.set_role(user_id, role)
        logger and logger.info("Role %s assigned to %s", role, user_id)

    async def get_role(self, user_id: int):
        return await self.role_repo.get_role(user_id)
