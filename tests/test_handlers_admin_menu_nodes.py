from __future__ import annotations

import pytest

from bot.constants import Role
from bot.handlers import admin as admin_handlers
from bot.handlers import menu as menu_handlers
from bot.utils.errors import PermissionDenied

from .conftest import make_callback_update, make_message_update


@pytest.mark.asyncio
async def test_admin_entry_requires_moderator(context, services):
    await services.profile.ensure_user(1, "u", "User One")
    update = make_message_update(1, text="⚙️ Админка")
    with pytest.raises(PermissionDenied):
        await admin_handlers.admin_entry(update, context)

    await services.profile.assign_role(1, Role.MODERATOR)
    await admin_handlers.admin_entry(update, context)
    assert update.message.replies
    assert "Админ-панель" in update.message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_admin_login_check_password(context, services):
    await services.profile.ensure_user(1, "u", "User One")

    # wrong password
    update = make_message_update(1, text="wrong")
    res = await admin_handlers.admin_login_check(update, context)
    assert res is not None
    assert "Неверный" in update.message.replies[-1]["text"]

    # correct password -> admin role
    update2 = make_message_update(1, text="secret")
    res2 = await admin_handlers.admin_login_check(update2, context)
    assert res2 is not None
    assert (await services.profile.get_role(1)) == Role.ADMIN


@pytest.mark.asyncio
async def test_node_cms_start_renders_root_list(context, services, seeded_nodes):
    await services.profile.ensure_user(1, "u", "User One")
    await services.profile.assign_role(1, Role.ADMIN)

    update = make_callback_update(1, data="admin_cms")
    await admin_handlers.node_cms_start(update, context)
    edits = update.callback_query.edits
    assert edits
    kb = edits[-1]["reply_markup"]
    labels = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any("Добавить корневой" in t for t in labels)


@pytest.mark.asyncio
async def test_main_menu_router_unknown_shows_menu(context, monkeypatch):
    called = {"n": 0}

    async def fake_send_main_menu(ctx, chat_id: int, text: str = "Главное меню"):
        called["n"] += 1

    monkeypatch.setattr(menu_handlers, "send_main_menu", fake_send_main_menu)

    update = make_message_update(1, text="???")
    await menu_handlers.main_menu_router(update, context)
    assert called["n"] == 1

