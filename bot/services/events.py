from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from ..models import Event, Registration
from ..utils.errors import ValidationError
from ..utils.validators import parse_int
from ..logging_config import logger


def _parse_datetime(dt: str) -> datetime:
    try:
        return datetime.strptime(dt, "%Y-%m-%d %H:%M")
    except ValueError as ex:
        raise ValidationError("Дата должна быть в формате YYYY-MM-DD HH:MM") from ex


class EventService:
    def __init__(self, event_repo, reg_repo):
        self.event_repo = event_repo
        self.reg_repo = reg_repo

    @staticmethod
    def _is_active_reg_status(status: str) -> bool:
        return status not in ("cancelled", "canceled")

    async def list_active_events(self) -> List[Event]:
        events = await self.event_repo.list_events()
        now = datetime.now()
        return [e for e in events if _parse_datetime(e.datetime_str) > now]

    async def get_event(self, event_id: str) -> Optional[Event]:
        return await self.event_repo.get(event_id)

    async def add_event(self, name: str, datetime_str: str, description: str, seats: int) -> Event:
        _parse_datetime(datetime_str)
        if seats <= 0:
            raise ValidationError("Количество мест должно быть > 0")
        events = await self.event_repo.list_events()
        event_id = f"event_{len(events) + 1}"
        event = Event(event_id=event_id, name=name.strip(), datetime_str=datetime_str, description=description.strip(), max_seats=seats)
        await self.event_repo.add(event)
        return event

    async def update_event_field(self, event_id: str, field: str, value: str) -> Event:
        event = await self.get_event(event_id)
        if not event:
            raise ValidationError("Мероприятие не найдено")
        if field == "name":
            event.name = value.strip()
        elif field == "datetime_str":
            _parse_datetime(value)
            event.datetime_str = value.strip()
        elif field == "description":
            event.description = value.strip()
        elif field == "max_seats":
            seats = parse_int(value)
            if not seats or seats <= 0:
                raise ValidationError("Некорректное число мест")
            event.max_seats = seats
        else:
            raise ValidationError("Неизвестное поле")
        await self.event_repo.update(event)
        return event

    async def delete_event(self, event_id: str):
        await self.event_repo.delete(event_id)
        await self.reg_repo.delete_by_event(event_id)

    async def register_user(self, user_id: int, event_id: str) -> Registration:
        existing = await self.reg_repo.get(user_id, event_id)
        if existing:
            raise ValidationError("Вы уже зарегистрированы")
        event = await self.get_event(event_id)
        if not event:
            raise ValidationError("Мероприятие не найдено")
        regs = await self.reg_repo.list_by_event(event_id)
        active_regs = [r for r in regs if self._is_active_reg_status(r.status)]
        if len(active_regs) >= event.max_seats:
            raise ValidationError("Нет свободных мест")
        reg = Registration(id=None, user_id=user_id, event_id=event_id, status="registered")
        reg_id = await self.reg_repo.create(reg)
        reg.id = reg_id
        return reg

    async def confirm_registration(self, user_id: int, event_id: str) -> Registration:
        reg = await self.reg_repo.get(user_id, event_id)
        if not reg:
            raise ValidationError("Регистрация не найдена")
        await self.reg_repo.update_status(reg.id, "confirmed")  # type: ignore[arg-type]
        logger and logger.info("User %s confirmed event %s", user_id, event_id)
        return await self.reg_repo.get(user_id, event_id)  # type: ignore[return-value]

    async def confirm_or_register(self, user_id: int, event_id: str) -> Registration:
        """Кнопка 'подтвердить' должна работать и после напоминаний от админа."""
        reg = await self.reg_repo.get(user_id, event_id)
        if not reg:
            reg = await self.register_user(user_id, event_id)
        if reg.status != "confirmed":
            reg = await self.confirm_registration(user_id, event_id)
        return reg

    async def cancel_registration(self, user_id: int, event_id: str) -> Registration:
        reg = await self.reg_repo.get(user_id, event_id)
        if not reg:
            raise ValidationError("Регистрация не найдена")
        if reg.status in ("cancelled", "canceled"):
            return reg
        await self.reg_repo.update_status(reg.id, "cancelled")  # type: ignore[arg-type]
        return await self.reg_repo.get(user_id, event_id)  # type: ignore[return-value]

    async def get_user_registration(self, user_id: int, event_id: str) -> Optional[Registration]:
        return await self.reg_repo.get(user_id, event_id)

    async def list_user_registrations(self, user_id: int, only_active: bool = True) -> List[Registration]:
        regs = await self.reg_repo.list_by_user(user_id)
        if not only_active:
            return regs
        return [r for r in regs if self._is_active_reg_status(r.status)]

    async def list_registrations(self, event_id: str) -> List[Registration]:
        return await self.reg_repo.list_by_event(event_id)

