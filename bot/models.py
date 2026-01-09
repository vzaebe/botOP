from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .constants import Role


def utcnow_str() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class User:
    user_id: int
    username: str = ""
    full_name: str = ""
    email: str = ""
    consent: bool = False
    consent_time: Optional[str] = None
    created_at: str = utcnow_str()
    updated_at: str = utcnow_str()


@dataclass
class Event:
    event_id: str
    name: str
    datetime_str: str
    description: str
    max_seats: int


@dataclass
class Registration:
    id: Optional[int]
    user_id: int
    event_id: str
    status: str = "registered"
    reg_time: str = utcnow_str()


@dataclass
class ContentSection:
    key: str
    title: str
    body: str


@dataclass
class MenuItem:
    key: str
    title: str
    position: int


@dataclass
class Template:
    key: str
    body: str

