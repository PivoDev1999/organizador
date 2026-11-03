"""Agenda (events). The recurrence rule lives in `app.core.agenda`; the repository only narrows the rows
that may fall in a range, and this service expands them into occurrences."""

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.core.agenda import event_problem, occurrences
from app.core.errors import NotFoundError, ValidationError
from app.core.storage import Storage
from app.models import Event
from app.models.file import FileEntityType
from app.repositories import event as event_repo
from app.schemas.event import EventCreate, EventQuery, EventUpdate
from app.services import files as files_service

# The dashboard shows the occurrences from today to today + 7 days (fixed, not the `within` of the query).
UPCOMING_DAYS = 7


class EventNotFound(NotFoundError):
    detail = "Evento não encontrado."


class InvalidEvent(ValidationError):
    """Times or repetition that do not fit together; always raised with the message of `event_problem`."""


@dataclass(frozen=True)
class Occurrence:
    date: date
    event: Event


def list_occurrences(
    db: Session, user_id: uuid.UUID, date_from: date, date_to: date, search: str | None = None
) -> list[Occurrence]:
    """Every occurrence of the user's events between `date_from` and `date_to` (inclusive), by date,
    then all-day events first, start time, title (pt-BR) and id.

    The repository returns the candidate events already in the order of a day, so a stable sort by date
    keeps it. The schema caps the range (366 days), which caps the expansion too.
    """
    result = [
        Occurrence(day, event)
        for event in event_repo.list_in_range(db, user_id, date_from, date_to, search)
        for day in occurrences(event.starts_on, event.recurrence, event.repeat_until, date_from, date_to)
    ]
    result.sort(key=lambda occurrence: occurrence.date)
    return result


def list_events(db: Session, user_id: uuid.UUID, query: EventQuery) -> list[Occurrence]:
    return list_occurrences(db, user_id, query.date_from, query.date_to, query.q)


def list_upcoming_preview(
    db: Session, user_id: uuid.UUID, today: date, limit: int
) -> tuple[list[Occurrence], int]:
    """The first `limit` occurrences from `today` to `today + 7` days, plus how many there are in all."""
    upcoming = list_occurrences(db, user_id, today, today + timedelta(days=UPCOMING_DAYS))
    return upcoming[:limit], len(upcoming)


def get_event(db: Session, user_id: uuid.UUID, event_id: uuid.UUID, *, for_update: bool = False) -> Event:
    """The user's event. Someone else's event is reported as missing (404), never as forbidden."""
    event = event_repo.get_for_user(db, user_id, event_id, for_update=for_update)
    if event is None:
        raise EventNotFound
    return event


def create_event(db: Session, user_id: uuid.UUID, data: EventCreate) -> Event:
    # The schema already checked times and repetition (no stored state is involved on create).
    event = Event(user_id=user_id, **data.model_dump())
    event_repo.add(db, event)
    db.commit()
    return event


def update_event(db: Session, user_id: uuid.UUID, event_id: uuid.UUID, data: EventUpdate) -> Event:
    """Apply a partial update, checking times and repetition on the combined state (stored row +
    changes), so a PATCH can never leave the event incoherent. Nothing is cleared implicitly: turning
    the repetition off with a `repeat_until` stored is a 422 unless the body clears it too."""
    event = get_event(db, user_id, event_id, for_update=True)
    requested = data.model_dump(exclude_unset=True)

    def final(field: str):
        return requested.get(field, getattr(event, field))

    problem = event_problem(
        final("starts_on"), final("start_time"), final("end_time"), final("recurrence"), final("repeat_until")
    )
    if problem:
        db.rollback()  # release the row lock now
        raise InvalidEvent(problem)

    changes = {field: value for field, value in requested.items() if getattr(event, field) != value}
    if not changes:
        # Nothing to write: end the transaction (no UPDATE, updated_at untouched) and release the lock.
        db.commit()
        return event
    for field, value in changes.items():
        setattr(event, field, value)
    event_repo.save(db)
    db.commit()
    return event


def delete_event(db: Session, storage: Storage, user_id: uuid.UUID, event_id: uuid.UUID) -> None:
    event = get_event(db, user_id, event_id, for_update=True)
    event_repo.delete(db, event)
    keys = files_service.delete_attachments(db, user_id, FileEntityType.EVENT, [event_id])
    db.commit()
    files_service.purge_objects(storage, keys)
