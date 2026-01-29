from __future__ import annotations

import pytest

from bot.constants import Conversation
from bot.handlers import events as events_handlers
from bot.handlers import profile as profile_handlers
from bot.handlers import start as start_handlers
from bot.services.messaging import MENU_LABEL_EVENTS, MENU_LABEL_PROFILE
from bot.utils.errors import ValidationError

from .conftest import make_callback_update, make_message_update


@pytest.mark.asyncio
async def test_start_requires_consent_on_first_run(context):
    update = make_message_update(1, text="/start", username="u", full_name="User One")
    state = await start_handlers.start(update, context)
    assert state == Conversation.CONFIRM_PROFILE
    assert update.message.replies
    assert "согласие" in update.message.replies[-1]["text"].lower()


@pytest.mark.asyncio
async def test_consent_accept_sets_flag_and_shows_menu(context, services):
    await services.profile.ensure_user(1, "u", "User One")
    update = make_callback_update(1, data="consent_accept")

    await start_handlers.consent_accept(update, context)
    assert update.callback_query.answered == 1
    assert any("согласие" in e["text"].lower() for e in update.callback_query.edits if e.get("kind") == "text")
    profile = await services.profile.get_profile(1)
    assert profile is not None and profile.consent is True
    assert context.bot.sent_messages  # menu was sent


@pytest.mark.asyncio
async def test_show_profile_requires_consent(context, services):
    await services.profile.ensure_user(1, "u", "User One")
    update = make_message_update(1, text=MENU_LABEL_PROFILE)

    res = await profile_handlers.show_profile(update, context)
    assert res is not None
    assert update.message.replies
    assert "/start" in update.message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_show_profile_renders_when_consented(context, services):
    await services.profile.ensure_user(1, "u", "User One")
    await services.profile.set_consent(1, True)
    update = make_message_update(1, text=MENU_LABEL_PROFILE)

    await profile_handlers.show_profile(update, context)
    assert update.message.replies
    text = update.message.replies[-1]["text"]
    assert "Профиль" in text
    assert "Согласие" in text


@pytest.mark.asyncio
async def test_profile_save_name_validation_loop(context, services):
    await services.profile.ensure_user(1, "u", "User One")
    await services.profile.set_consent(1, True)
    update = make_message_update(1, text="ab")

    state = await profile_handlers.save_name(update, context)
    assert state == Conversation.INPUT_NAME
    assert "⚠️" in update.message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_list_events_no_active(context, services):
    update = make_message_update(1, text=MENU_LABEL_EVENTS)
    await events_handlers.list_events(update, context)
    assert "активных событий нет" in update.message.replies[-1]["text"].lower()


@pytest.mark.asyncio
async def test_view_event_shows_register_action_when_not_registered(context, services, seeded_event):
    await services.profile.ensure_user(1, "u", "User One")
    await services.profile.set_consent(1, True)

    update = make_callback_update(1, data=f"event_view_{seeded_event.event_id}")
    await events_handlers.view_event(update, context)

    edits = update.callback_query.edits
    assert edits
    kb = edits[-1]["reply_markup"]
    callback_datas = [btn.callback_data for row in kb.inline_keyboard for btn in row if hasattr(btn, "callback_data")]
    assert any(cd.startswith("event_register_") for cd in callback_datas)


@pytest.mark.asyncio
async def test_start_registration_requests_missing_name(context, services, seeded_event):
    await services.profile.ensure_user(1, "u", "")
    await services.profile.set_consent(1, True)

    update = make_callback_update(1, data=f"event_register_{seeded_event.event_id}")
    state = await events_handlers.start_registration(update, context)
    assert state == Conversation.INPUT_NAME
    assert context.user_data["pending_event"] == seeded_event.event_id
    assert context.user_data["registration_flow"] == "name"


@pytest.mark.asyncio
async def test_confirm_registration_callback_registers_and_confirms(context, services, seeded_event):
    await services.profile.ensure_user(1, "u", "User One")
    await services.profile.update_email(1, "u@example.com")
    await services.profile.set_consent(1, True)

    update = make_callback_update(1, data=f"event_confirm_{seeded_event.event_id}")
    await events_handlers.confirm_registration_callback(update, context)

    reg = await services.event.get_user_registration(1, seeded_event.event_id)
    assert reg is not None
    assert reg.status == "confirmed"
    assert any("запись" in m["text"].lower() for m in context.bot.sent_messages)
