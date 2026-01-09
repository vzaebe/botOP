from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Optional

import pytest

from bot.config import Config
from bot.constants import Role
from bot.models import Event, Node, User
from bot.services.content import ContentService
from bot.services.events import EventService
from bot.services.nodes import NodeService
from bot.services.profiles import ProfileService
from bot.services.restart import RestartService
from bot.storage.db import Database
from bot.storage.repositories.content import ContentRepository
from bot.storage.repositories.events import EventRepository
from bot.storage.repositories.nodes import NodeRepository
from bot.storage.repositories.registrations import RegistrationRepository
from bot.storage.repositories.roles import RoleRepository
from bot.storage.repositories.users import UserRepository


@dataclass
class FakeUser:
    id: int
    username: str = ""
    full_name: str = ""


@dataclass
class FakeChat:
    id: int


@dataclass
class FakeMessage:
    chat_id: int
    text: str = ""
    chat: FakeChat = field(init=False)
    replies: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        self.chat = FakeChat(self.chat_id)

    async def reply_text(self, text: str, reply_markup: Any = None, **kwargs: Any):
        self.replies.append(
            {"text": text, "reply_markup": reply_markup, "kwargs": kwargs}
        )


@dataclass
class FakeCallbackQuery:
    data: str
    from_user: FakeUser
    message: FakeMessage
    answered: int = 0
    edits: list[dict[str, Any]] = field(default_factory=list)
    deleted: int = 0

    async def answer(self, **kwargs: Any):
        self.answered += 1

    async def edit_message_text(self, text: str, reply_markup: Any = None, **kwargs: Any):
        self.edits.append(
            {"text": text, "reply_markup": reply_markup, "kwargs": kwargs, "kind": "text"}
        )

    async def edit_message_reply_markup(self, reply_markup: Any = None, **kwargs: Any):
        self.edits.append(
            {"reply_markup": reply_markup, "kwargs": kwargs, "kind": "markup"}
        )

    async def delete_message(self, **kwargs: Any):
        self.deleted += 1


@dataclass
class FakeUpdate:
    effective_user: FakeUser
    effective_chat: FakeChat
    message: Optional[FakeMessage] = None
    callback_query: Optional[FakeCallbackQuery] = None


class FakeBot:
    def __init__(self):
        self.sent_messages: list[dict[str, Any]] = []
        self.sent_documents: list[dict[str, Any]] = []

    async def send_message(self, chat_id: int, text: str, reply_markup: Any = None, **kwargs: Any):
        payload = {"chat_id": chat_id, "text": text, "reply_markup": reply_markup, "kwargs": kwargs}
        self.sent_messages.append(payload)
        return SimpleNamespace(message_id=len(self.sent_messages), chat=SimpleNamespace(id=chat_id))

    async def send_document(self, chat_id: int, document: Any, filename: str = "", caption: str = "", **kwargs: Any):
        payload = {
            "chat_id": chat_id,
            "document": document,
            "filename": filename,
            "caption": caption,
            "kwargs": kwargs,
        }
        self.sent_documents.append(payload)
        return SimpleNamespace(message_id=len(self.sent_documents), chat=SimpleNamespace(id=chat_id))


class FakeApplication:
    def __init__(self, bot_data: dict[str, Any]):
        self.bot_data = bot_data

    async def stop(self):
        return None

    async def shutdown(self):
        return None


@dataclass
class FakeContext:
    application: FakeApplication
    bot: FakeBot
    user_data: dict[str, Any] = field(default_factory=dict)


def make_message_update(user_id: int, chat_id: Optional[int] = None, text: str = "", username: str = "", full_name: str = "") -> FakeUpdate:
    chat_id = chat_id if chat_id is not None else user_id
    user = FakeUser(id=user_id, username=username, full_name=full_name)
    chat = FakeChat(id=chat_id)
    msg = FakeMessage(chat_id=chat_id, text=text)
    return FakeUpdate(effective_user=user, effective_chat=chat, message=msg, callback_query=None)


def make_callback_update(
    user_id: int,
    data: str,
    chat_id: Optional[int] = None,
    username: str = "",
    full_name: str = "",
) -> FakeUpdate:
    chat_id = chat_id if chat_id is not None else user_id
    user = FakeUser(id=user_id, username=username, full_name=full_name)
    chat = FakeChat(id=chat_id)
    msg = FakeMessage(chat_id=chat_id, text="")
    cq = FakeCallbackQuery(data=data, from_user=user, message=msg)
    return FakeUpdate(effective_user=user, effective_chat=chat, message=None, callback_query=cq)


@pytest.fixture
async def db(tmp_path) -> Database:
    db_path = tmp_path / "test.db"
    database = Database(str(db_path))
    await database.init_db()
    try:
        yield database
    finally:
        if database._conn is not None:  # noqa: SLF001
            await database._conn.close()  # noqa: SLF001


@pytest.fixture
async def repos(db: Database):
    return SimpleNamespace(
        user=UserRepository(db),
        role=RoleRepository(db),
        event=EventRepository(db),
        reg=RegistrationRepository(db),
        content=ContentRepository(db),
        node=NodeRepository(db),
    )


@pytest.fixture
async def services(repos):
    return SimpleNamespace(
        profile=ProfileService(repos.user, repos.role),
        event=EventService(repos.event, repos.reg),
        content=ContentService(repos.content),
        node=NodeService(repos.node),
    )


@pytest.fixture
def fake_bot() -> FakeBot:
    return FakeBot()


@pytest.fixture
async def bot_data(services, db: Database):
    # Minimal config used by handlers
    cfg = Config(
        bot_token="TEST_TOKEN",
        admin_ids=[],
        admin_password="secret",
        database_path=":memory:",
        personal_data_link="https://example.test/personal",
        log_level="INFO",
        restart_enabled=True,
    )
    role_service = services.profile  # used by require_role
    return {
        "config": cfg,
        "db": db,
        "profile_service": services.profile,
        "event_service": services.event,
        "content_service": services.content,
        "node_service": services.node,
        "role_service": role_service,
        "restart_service": RestartService(enabled=False),
    }


@pytest.fixture
async def context(bot_data, fake_bot: FakeBot) -> FakeContext:
    return FakeContext(application=FakeApplication(bot_data), bot=fake_bot, user_data={})


@pytest.fixture
async def seeded_user(services) -> User:
    # A default-consented user for most handler tests
    u = await services.profile.ensure_user(1, "u", "User One")
    await services.profile.set_consent(1, True)
    return u


@pytest.fixture
async def seeded_event(services) -> Event:
    # A far future event so it's always active
    return await services.event.add_event(
        name="Test Event",
        datetime_str="2099-01-01 10:00",
        description="Desc",
        seats=2,
    )


@pytest.fixture
async def seeded_nodes(services) -> list[Node]:
    await services.node.ensure_defaults()
    return await services.node.get_all_nodes()

