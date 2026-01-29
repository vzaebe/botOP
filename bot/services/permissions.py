from __future__ import annotations

from functools import wraps
from typing import Any, Awaitable, Callable
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
            # Try to resolve user from different update shapes (message/callback/etc.)
            user = getattr(update, "effective_user", None)
            if not user:
                cq = getattr(update, "callback_query", None)
                if cq:
                    user = getattr(cq, "from_user", None)
            if not user and getattr(update, "message", None):
                user = getattr(update.message, "from_user", None)
            if not user:
                # Graceful fallback: notify and stop without crashing handlers.
                msg = "Не удалось определить пользователя, попробуйте ещё раз."
                eff_msg = getattr(update, "effective_message", None)
                if eff_msg:
                    try:
                        await eff_msg.reply_text(msg)
                    except Exception:
                        pass
                return None
            role_service = context.application.bot_data.get("role_service")
            if role_service is None:
                raise PermissionDenied("Role service not configured")
            # Auto-elevate configured admins even if БД не содержит записи
            cfg = context.application.bot_data.get("config")
            admin_ids = set()
            if cfg and getattr(cfg, "admin_ids", None):
                try:
                    admin_ids = {int(x) for x in cfg.admin_ids}
                except Exception:
                    admin_ids = set(cfg.admin_ids or [])

            if user.id in admin_ids:
                try:
                    await role_service.ensure_user(
                        user.id,
                        getattr(user, "username", "") or "",
                        getattr(user, "full_name", "") or "",
                    )
                    await role_service.assign_role(user.id, Role.ADMIN)
                except Exception:
                    # best-effort: если не смогли записать в БД, всё равно пропускаем
                    pass
                return await func(update, context, *args, **kwargs)

            user_role = await role_service.get_role(user.id)
            if not has_role(user_role, required):
                raise PermissionDenied(f"Need role {required}, got {user_role}")
            return await func(update, context, *args, **kwargs)

        return wrapper

    return decorator

