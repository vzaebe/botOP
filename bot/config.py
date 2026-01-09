from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List

from dotenv import load_dotenv


@dataclass
class Config:
    bot_token: str
    admin_ids: List[int]
    admin_password: str
    database_path: str
    personal_data_link: str
    log_level: str = "INFO"
    restart_enabled: bool = True


def _parse_admin_ids(raw: str) -> List[int]:
    ids: List[int] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            ids.append(int(chunk))
        except ValueError:
            continue
    return ids


def load_config() -> Config:
    load_dotenv()
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN is required. Set it in .env")

    admin_ids = _parse_admin_ids(os.getenv("ADMIN_IDS", ""))
    admin_password = os.getenv("ADMIN_PASSWORD", "")
    if not admin_password:
        raise RuntimeError("ADMIN_PASSWORD is required. Set it in .env")

    personal_link = os.getenv("PERSONAL_DATA_LINK", "<ВСТАВЬТЕ_ССЫЛКУ_ТУТ>")
    db_path = os.getenv("DATABASE_PATH", os.path.join("data", "bot.db"))
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    return Config(
        bot_token=token,
        admin_ids=admin_ids,
        admin_password=admin_password,
        database_path=db_path,
        personal_data_link=personal_link,
        log_level=log_level,
    )

