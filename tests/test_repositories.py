from __future__ import annotations

import pytest

from bot.constants import Role
from bot.models import ContentSection, Event, MenuItem, Node, Registration, Template


@pytest.mark.asyncio
async def test_user_repository_upsert_creates_default_role(repos):
    user = await repos.user.upsert_user(1, "u", "User One")
    assert user.user_id == 1
    assert (await repos.role.get_role(1)) == Role.USER


@pytest.mark.asyncio
async def test_user_repository_profile_fields_and_list(repos):
    await repos.user.upsert_user(1, "u", "User One")
    await repos.user.set_email(1, "u@example.com")
    await repos.user.set_full_name(1, "User Updated")
    await repos.user.set_consent(1, True)

    u = await repos.user.get_user(1)
    assert u is not None
    assert u.email == "u@example.com"
    assert u.full_name == "User Updated"
    assert u.consent is True
    assert u.consent_time

    users = await repos.user.list_users()
    assert len(users) == 1


@pytest.mark.asyncio
async def test_role_repository_default_and_set(repos):
    # No row -> default USER
    assert (await repos.role.get_role(999)) == Role.USER

    await repos.user.upsert_user(1, "u", "User One")
    await repos.role.set_role(1, Role.ADMIN)
    assert (await repos.role.get_role(1)) == Role.ADMIN

    roles = await repos.role.list_roles()
    assert (1, Role.ADMIN) in roles


@pytest.mark.asyncio
async def test_event_repository_crud(repos):
    e = Event(event_id="event_1", name="Name", datetime_str="2099-01-01 10:00", description="D", max_seats=10)
    await repos.event.add(e)
    got = await repos.event.get("event_1")
    assert got is not None
    assert got.name == "Name"

    e.name = "Name 2"
    await repos.event.update(e)
    got2 = await repos.event.get("event_1")
    assert got2 is not None
    assert got2.name == "Name 2"

    events = await repos.event.list_events()
    assert [ev.event_id for ev in events] == ["event_1"]

    await repos.event.delete("event_1")
    assert await repos.event.get("event_1") is None


@pytest.mark.asyncio
async def test_registration_repository_crud(repos):
    await repos.user.upsert_user(1, "u", "User One")
    await repos.event.add(Event("event_1", "Name", "2099-01-01 10:00", "D", 10))

    reg = Registration(id=None, user_id=1, event_id="event_1", status="registered")
    reg_id = await repos.reg.create(reg)
    assert reg_id > 0

    got = await repos.reg.get(1, "event_1")
    assert got is not None
    assert got.status == "registered"

    await repos.reg.update_status(reg_id, "confirmed")
    got2 = await repos.reg.get(1, "event_1")
    assert got2 is not None
    assert got2.status == "confirmed"

    by_event = await repos.reg.list_by_event("event_1")
    assert len(by_event) == 1

    by_user = await repos.reg.list_by_user(1)
    assert len(by_user) == 1

    await repos.reg.delete_by_event("event_1")
    assert await repos.reg.get(1, "event_1") is None


@pytest.mark.asyncio
async def test_content_repository_sections_menu_templates(repos):
    await repos.content.upsert_section(ContentSection("k", "t", "b"))
    assert (await repos.content.get_section("k")).title == "t"  # type: ignore[union-attr]
    assert [s.key for s in await repos.content.list_sections()] == ["k"]

    await repos.content.upsert_menu_item(MenuItem("m1", "Menu 1", 2))
    await repos.content.upsert_menu_item(MenuItem("m0", "Menu 0", 1))
    assert [m.key for m in await repos.content.list_menu_items()] == ["m0", "m1"]
    await repos.content.delete_menu_item("m0")
    assert [m.key for m in await repos.content.list_menu_items()] == ["m1"]

    await repos.content.upsert_template(Template("tpl", "body"))
    assert (await repos.content.get_template("tpl")).body == "body"  # type: ignore[union-attr]
    assert {t.key for t in await repos.content.list_templates()} == {"tpl"}


@pytest.mark.asyncio
async def test_node_repository_tree_and_main_menu(repos):
    root_id = await repos.node.upsert_node(Node(id=None, parent_id=None, key="root", title="Root", content="C", is_main_menu=True))
    child_id = await repos.node.upsert_node(Node(id=None, parent_id=root_id, key="child", title="Child", content="CC", order_index=2))

    assert (await repos.node.get_node(root_id)).title == "Root"  # type: ignore[union-attr]
    assert (await repos.node.get_node(child_id)).parent_id == root_id  # type: ignore[union-attr]
    assert (await repos.node.get_node_by_key("child")).id == child_id  # type: ignore[union-attr]

    roots = await repos.node.get_children(None)
    assert [n.id for n in roots] == [root_id]

    children = await repos.node.get_children(root_id)
    assert [n.id for n in children] == [child_id]

    main = await repos.node.get_main_menu_nodes()
    assert [n.id for n in main] == [root_id]

