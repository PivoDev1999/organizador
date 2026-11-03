import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Event, EventRecurrence
from app.repositories.errors import flush
from app.repositories.search import LIKE_ESCAPE, TEXT_SORT_COLLATION, escape_like


def get_for_user(
    db: Session, user_id: uuid.UUID, event_id: uuid.UUID, *, for_update: bool = False
) -> Event | None:
    """The event if it belongs to the user. `for_update=True` locks the row and refreshes it (see
    `task.get_for_user`)."""
    stmt = select(Event).where(Event.id == event_id, Event.user_id == user_id)
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return db.scalar(stmt)


def exists_for_user(db: Session, user_id: uuid.UUID, event_id: uuid.UUID) -> bool:
    """Whether the event belongs to the user, holding a FOR KEY SHARE lock until commit (attachments)."""
    stmt = (
        select(Event.id)
        .where(Event.id == event_id, Event.user_id == user_id)
        .with_for_update(read=True, key_share=True)  # FOR KEY SHARE (key_share alone is NO KEY UPDATE)
    )
    return db.scalar(stmt) is not None


def list_in_range(
    db: Session, user_id: uuid.UUID, date_from: date, date_to: date, search: str | None = None
) -> list[Event]:
    """The user's events that may happen between `date_from` and `date_to` (inclusive), optionally only
    those with `search` (literal, case-insensitive) in the title, description or location.

    One-off events must start inside the range; recurring ones must start by its end and not stop
    repeating before its start. Which days they actually fall on is `app.core.agenda.occurrences`.
    Ordered all-day first, then start time, title (pt-BR) and id: the tie-break order of a day, which the
    service keeps with a stable sort by date.
    """
    one_off = (Event.recurrence == EventRecurrence.NONE.value) & (Event.starts_on >= date_from)
    recurring = (Event.recurrence != EventRecurrence.NONE.value) & (
        Event.repeat_until.is_(None) | (Event.repeat_until >= date_from)
    )
    stmt = select(Event).where(Event.user_id == user_id, Event.starts_on <= date_to, one_off | recurring)
    if search is not None:
        pattern = f"%{escape_like(search)}%"
        stmt = stmt.where(
            Event.title.ilike(pattern, escape=LIKE_ESCAPE)
            | Event.description.ilike(pattern, escape=LIKE_ESCAPE)
            | Event.location.ilike(pattern, escape=LIKE_ESCAPE)
        )
    stmt = stmt.order_by(
        Event.start_time.asc().nulls_first(),
        Event.title.collate(TEXT_SORT_COLLATION).asc(),
        Event.id.asc(),
    )
    return list(db.scalars(stmt).all())


def add(db: Session, event: Event) -> Event:
    db.add(event)
    flush(db)
    return event


def save(db: Session) -> None:
    flush(db)


def delete(db: Session, event: Event) -> None:
    db.delete(event)
    flush(db)
