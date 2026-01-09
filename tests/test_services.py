from __future__ import annotations

import pytest

from bot.models import Event
from bot.utils.errors import ValidationError


@pytest.mark.asyncio
async def test_profile_service_validates_email_and_name(services):
    await services.profile.ensure_user(1, "u", "User One")

    with pytest.raises(ValidationError):
        await services.profile.update_email(1, "not-an-email")

    with pytest.raises(ValidationError):
        await services.profile.update_full_name(1, "ab")

    u = await services.profile.update_full_name(1, "User Updated")
    assert u.full_name == "User Updated"

    u2 = await services.profile.update_email(1, "u@example.com")
    assert u2.email == "u@example.com"


@pytest.mark.asyncio
async def test_event_service_add_validates_datetime_and_seats(services):
    with pytest.raises(ValidationError):
        await services.event.add_event("N", "bad", "D", 1)
    with pytest.raises(ValidationError):
        await services.event.add_event("N", "2099-01-01 10:00", "D", 0)


@pytest.mark.asyncio
async def test_event_service_list_active_filters_past(services):
    await services.event.event_repo.add(
        Event(
            event_id="past",
            name="Past",
            datetime_str="2000-01-01 10:00",
            description="D",
            max_seats=1,
        )
    )
    await services.event.event_repo.add(
        Event(
            event_id="future",
            name="Future",
            datetime_str="2099-01-01 10:00",
            description="D",
            max_seats=1,
        )
    )
    active = await services.event.list_active_events()
    assert [e.event_id for e in active] == ["future"]


@pytest.mark.asyncio
async def test_event_service_registration_flow_and_capacity(services):
    await services.profile.ensure_user(1, "u", "User One")
    await services.profile.ensure_user(2, "u2", "User Two")

    ev = await services.event.add_event("Event", "2099-01-01 10:00", "D", seats=1)

    reg1 = await services.event.register_user(1, ev.event_id)
    assert reg1.id is not None

    with pytest.raises(ValidationError):
        await services.event.register_user(1, ev.event_id)

    with pytest.raises(ValidationError):
        await services.event.register_user(2, ev.event_id)

    confirmed = await services.event.confirm_or_register(1, ev.event_id)
    assert confirmed.status == "confirmed"

    cancelled = await services.event.cancel_registration(1, ev.event_id)
    assert cancelled.status in ("cancelled", "canceled")

    # After cancellation, slot is free
    reg2 = await services.event.register_user(2, ev.event_id)
    assert reg2.user_id == 2


@pytest.mark.asyncio
async def test_event_service_list_user_registrations_only_active(services):
    await services.profile.ensure_user(1, "u", "User One")
    ev = await services.event.add_event("Event", "2099-01-01 10:00", "D", seats=2)
    await services.event.register_user(1, ev.event_id)
    await services.event.cancel_registration(1, ev.event_id)

    active = await services.event.list_user_registrations(1, only_active=True)
    assert active == []
    all_regs = await services.event.list_user_registrations(1, only_active=False)
    assert len(all_regs) == 1


@pytest.mark.asyncio
async def test_content_service_ensure_defaults_idempotent(services):
    await services.content.ensure_defaults()
    sections1 = await services.content.list_sections()
    menu1 = await services.content.list_menu_items()
    templates1 = await services.content.list_templates()

    await services.content.ensure_defaults()
    sections2 = await services.content.list_sections()
    menu2 = await services.content.list_menu_items()
    templates2 = await services.content.list_templates()

    assert len(sections2) == len(sections1)
    assert len(menu2) == len(menu1)
    assert len(templates2) == len(templates1)


@pytest.mark.asyncio
async def test_node_service_ensure_defaults_creates_tree(services):
    await services.node.ensure_defaults()
    nodes = await services.node.get_all_nodes()
    assert nodes
    main = await services.node.get_main_menu_nodes()
    assert any(n.is_main_menu for n in main)

