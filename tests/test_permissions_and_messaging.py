from __future__ import annotations

import pytest

from bot.constants import Role
from bot.services.messaging import send_main_menu
from bot.services.permissions import has_role, require_role
from bot.utils.errors import PermissionDenied

from .conftest import make_message_update


def test_has_role_ordering():
    assert has_role(Role.ADMIN, Role.USER) is True
    assert has_role(Role.ADMIN, Role.MODERATOR) is True
    assert has_role(Role.MODERATOR, Role.ADMIN) is False
    assert has_role(Role.USER, Role.USER) is True


@pytest.mark.asyncio
async def test_require_role_allows_and_denies(context, services):
    called = {"ok": 0}

    @require_role(Role.MODERATOR)
    async def handler(update, ctx):
        called["ok"] += 1
        return "ok"

    # Ensure user exists for FK on roles, and keep default role USER
    await services.profile.ensure_user(1, "u", "User One")
    update = make_message_update(1, text="hi")

    with pytest.raises(PermissionDenied):
        await handler(update, context)  # default is USER

    await services.profile.assign_role(1, Role.MODERATOR)
    res = await handler(update, context)
    assert res == "ok"
    assert called["ok"] == 1


@pytest.mark.asyncio
async def test_send_main_menu_includes_admin_button_for_admin(context, services, seeded_nodes):
    await services.profile.ensure_user(1, "u", "User One")

    # USER: no admin button
    await send_main_menu(context, chat_id=1, text="menu")
    kb = context.bot.sent_messages[-1]["reply_markup"]
    rows = [[btn.text for btn in row] for row in kb.keyboard]
    assert "⚙️ Админка" not in [t for row in rows for t in row]

    # ADMIN: admin button present
    await services.profile.assign_role(1, Role.ADMIN)
    await send_main_menu(context, chat_id=1, text="menu")
    kb2 = context.bot.sent_messages[-1]["reply_markup"]
    rows2 = [[btn.text for btn in row] for row in kb2.keyboard]
    assert "⚙️ Админка" in [t for row in rows2 for t in row]

