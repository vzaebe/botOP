from __future__ import annotations

from functools import wraps
from typing import Callable, Awaitable, Any
from telegram import Update
from telegram.ext import ContextTypes

from ..constants import Role
from ..utils.errors import PermissionDenied


ROLE_ORDER = {
    Role.USER: 0,
    Role.MODERATOR: 1,
    Role.ADMIN: 2,
}


def has_role(user_role: Role, required: Role) -> bool:
    return ROLE_ORDER[user_role] >= ROLE_ORDER[required]


def require_role(required: Role):
    def decorator(func: Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[Any]]):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            role_service = context.application.bot_data["role_service"]
            user_role = await role_service.get_role(update.effective_user.id)
            if not has_role(user_role, required):
                raise PermissionDenied(f"Need role {required}, got {user_role}")
            return await func(update, context, *args, **kwargs)

        return wrapper

    return decorator

