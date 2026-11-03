"""Calendar (calendário): agenda events, tasks, bills and pet reminders of a range in one list.

Read only, with no table of its own: each kind comes from the module that owns its rule (event
recurrence, open tasks, pending expenses, the reminder series). All reads run in one REPEATABLE READ,
READ ONLY transaction (`snapshot_repo.begin_read_snapshot`, as the dashboard), so the kinds reflect the
same instant.
"""

import uuid
from dataclasses import dataclass
from datetime import date, time

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.repositories import snapshot as snapshot_repo
from app.schemas.calendar import CalendarKind
from app.services import event as event_service
from app.services import pet as pet_service
from app.services import task as task_service
from app.services import transaction as transaction_service


@dataclass(frozen=True)
class CalendarEntry:
    kind: CalendarKind
    date: date
    time: time | None
    # The ORM row behind the entry: Event, Task, Transaction or PetEvent.
    record: object
    pet_name: str | None = None


def _order(entry: CalendarEntry) -> tuple[date, bool, time]:
    # All-day entries (no time) first, then by time.
    return entry.date, entry.time is not None, entry.time or time.min


def get_calendar(
    db: Session, settings: Settings, user_id: uuid.UUID, date_from: date, date_to: date
) -> list[CalendarEntry]:
    """Every entry between `date_from` and `date_to` (inclusive), by date, all-day first, then time.

    Ties keep the kind order (event, task, bill, pet) and, inside a kind, the order of its source: the
    sort is stable and each source is already sorted (events by time, title and id; tasks and bills by
    id; pet reminders by pet name and id).

    Only entries dated inside the range come in: overdue tasks, bills and reminders from before
    `date_from` stay out (the dashboard is where overdue items show up).
    """
    # No cap on the number of entries: the range itself (at most 366 days, checked by the schema) is the
    # limit, and a household has far fewer tasks, bills and reminders in a year than would matter.
    snapshot_repo.begin_read_snapshot(db, require=settings.dashboard_require_snapshot)
    entries = [
        CalendarEntry(CalendarKind.EVENT, item.date, item.event.start_time, item.event)
        for item in event_service.list_occurrences(db, user_id, date_from, date_to)
    ]
    entries += [
        CalendarEntry(CalendarKind.TASK, task.due_date, None, task)
        for task in task_service.list_open_due_between(db, user_id, date_from, date_to)
    ]
    entries += [
        CalendarEntry(CalendarKind.BILL, bill.due_date, None, bill)
        for bill in transaction_service.list_bills_between(db, user_id, date_from, date_to)
    ]
    entries += [
        CalendarEntry(CalendarKind.PET, event.next_due_on, None, event, pet_name)
        for event, pet_name in pet_service.list_reminders_between(db, user_id, date_from, date_to)
    ]
    entries.sort(key=_order)
    return entries
