import datetime
import uuid
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, Field

from app.models.event import EventRecurrence
from app.models.pet import PetEventType
from app.models.task import TaskPriority, TaskStatus
from app.schemas.common import Money

if TYPE_CHECKING:  # services import schemas: no runtime import back
    from app.services.calendar import CalendarEntry


class CalendarKind(StrEnum):
    EVENT = "event"
    TASK = "task"
    BILL = "bill"
    PET = "pet"


class _CalendarItemBase(BaseModel):
    date: datetime.date
    title: str
    time: datetime.time | None = Field(description="Horário; null para itens de dia inteiro.")


class CalendarEventItem(_CalendarItemBase):
    """One occurrence of an agenda event (`id` is the event: GET /api/events/{id})."""

    kind: Literal["event"]
    id: uuid.UUID
    end_time: datetime.time | None
    location: str | None
    recurrence: EventRecurrence


class CalendarTaskItem(_CalendarItemBase):
    """A task not done, due on `date` (`id` is the task)."""

    kind: Literal["task"]
    id: uuid.UUID
    status: TaskStatus
    priority: TaskPriority


class CalendarBillItem(_CalendarItemBase):
    """A pending expense due on `date` (`id` is the transaction). `title` is the description, or the
    category when there is none."""

    kind: Literal["bill"]
    id: uuid.UUID
    amount: Money
    category: str


class CalendarPetItem(_CalendarItemBase):
    """A pet reminder due on `date` (`id` is the pet event, `pet_id` its pet). `title` is the pet name."""

    kind: Literal["pet"]
    id: uuid.UUID
    pet_id: uuid.UUID
    pet_name: str
    type: PetEventType
    description: str | None


CalendarItemRead = Annotated[
    CalendarEventItem | CalendarTaskItem | CalendarBillItem | CalendarPetItem, Field(discriminator="kind")
]


def calendar_item(entry: "CalendarEntry") -> CalendarItemRead:
    """Build the item of one service entry (its ORM record plus the computed date and time)."""
    record = entry.record
    common = {"date": entry.date, "time": entry.time}
    match entry.kind:
        case CalendarKind.EVENT:
            return CalendarEventItem(
                kind="event",
                id=record.id,
                title=record.title,
                end_time=record.end_time,
                location=record.location,
                recurrence=record.recurrence,
                **common,
            )
        case CalendarKind.TASK:
            return CalendarTaskItem(
                kind="task",
                id=record.id,
                title=record.title,
                status=record.status,
                priority=record.priority,
                **common,
            )
        case CalendarKind.BILL:
            return CalendarBillItem(
                kind="bill",
                id=record.id,
                title=record.description or record.category,
                amount=record.amount,
                category=record.category,
                **common,
            )
        case CalendarKind.PET:
            return CalendarPetItem(
                kind="pet",
                id=record.id,
                title=entry.pet_name,
                pet_id=record.pet_id,
                pet_name=entry.pet_name,
                type=record.type,
                description=record.description,
                **common,
            )
    raise ValueError("unknown calendar kind")
