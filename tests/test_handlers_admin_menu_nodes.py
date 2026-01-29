from __future__ import annotations

import pytest

from bot.constants import Role, Conversation
from telegram.ext import ConversationHandler
from bot.handlers import admin as admin_handlers
from bot.handlers import menu as menu_handlers
from bot.services.messaging import ADMIN_BUTTON_TEXT, DEFAULT_MENU_TEXT
from bot.utils.errors import PermissionDenied

from .conftest import make_callback_update, make_message_update


@pytest.mark.asyncio
async def test_admin_entry_requires_moderator(context, services):
    await services.profile.ensure_user(1, "u", "User One")
    update = make_message_update(1, text=ADMIN_BUTTON_TEXT)
    with pytest.raises(PermissionDenied):
        await admin_handlers.admin_entry(update, context)

    await services.profile.assign_role(1, Role.MODERATOR)
    await admin_handlers.admin_entry(update, context)
    assert update.message.replies
    assert "Админ-панель" in update.message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_admin_login_check_password(context, services):
    await services.profile.ensure_user(1, "u", "User One")

    update = make_message_update(1, text="wrong")
    res = await admin_handlers.admin_login_check(update, context)
    assert res is not None
    assert "пароль" in update.message.replies[-1]["text"].lower()

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
    assert any("Добавить корневой раздел" in t for t in labels)


@pytest.mark.asyncio
async def test_admin_can_reparent_node(context, services, seeded_nodes):
    await services.profile.ensure_user(1, "u", "User One")
    await services.profile.assign_role(1, Role.ADMIN)

    child = next(n for n in seeded_nodes if n.parent_id is not None)
    old_parent = child.parent_id

    # Start reparent flow -> should show options
    update_start = make_callback_update(1, data=f"adm_node_reparent_{child.id}")
    await admin_handlers.adm_node_reparent_start(update_start, context)
    kb = update_start.callback_query.edits[-1]["reply_markup"]
    labels = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any("В корень" in t for t in labels)

    # Apply reparent to root
    update_apply = make_callback_update(1, data=f"adm_node_reparent_pick_{child.id}_root")
    await admin_handlers.adm_node_reparent_apply(update_apply, context)

    updated = await services.node.get_node(child.id)
    assert updated.parent_id is None
    assert updated.parent_id != old_parent


@pytest.mark.asyncio
async def test_main_menu_router_unknown_shows_menu(context, monkeypatch):
    called = {"n": 0}

    async def fake_send_main_menu(ctx, chat_id: int, text: str = DEFAULT_MENU_TEXT):
        called["n"] += 1

    monkeypatch.setattr(menu_handlers, "send_main_menu", fake_send_main_menu)

    update = make_message_update(1, text="???")
    await menu_handlers.main_menu_router(update, context)
    assert called["n"] == 1



@pytest.mark.asyncio
async def test_admin_can_add_admin_by_id(context, services):
    await services.profile.ensure_user(1, "u", "User One")
    await services.profile.assign_role(1, Role.ADMIN)

    # start flow
    start_update = make_callback_update(1, data="admin_add_admin")
    state = await admin_handlers.admin_add_admin_start(start_update, context)
    assert state == Conversation.ADMIN_ADD_ID

    apply_update = make_message_update(1, text="42")
    end_state = await admin_handlers.admin_add_admin_apply(apply_update, context)
    assert end_state == ConversationHandler.END
    assert (await services.profile.get_role(42)) == Role.ADMIN
