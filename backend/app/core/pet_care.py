"""Pure reminder rules of pet events: no database, no clock. The reference for SQL and tests alike.

A pet event with `next_due_on` (a booster shot, the next dose) is a reminder until a newer event of the
same series is recorded. A series is (pet, type, normalized description): "V10" in 10/2025 with a
booster due in 10/2026 is resolved by registering "v10 " in 10/2026, but not by "Antirrábica" nor by
another type. "Newer" means a later `occurred_on`, then `created_at`, then `id`, so only the latest
event of each series can be a reminder.

Normalization: `strip(" ")` + `str.lower()`, with None (no description) as its own key, equal to
itself. Whitespace inside the text is kept as is ("V\n10" and "V10" are different series), and so are
leading/trailing tabs or newlines. `app.repositories.pet` uses the SQL twin
`lower(btrim(description) COLLATE "pt-BR-x-icu")`: `btrim` removes only spaces, like `strip(" ")`, and
ICU's lower case is the full Unicode mapping, like Python's (the database default collation, musl's
en_US, is not: it maps "İ" and the final sigma differently). The match holds up to Unicode 15, the
version of Python 3.12's `str.lower()`; the ICU in the Postgres image is newer, and 27 characters added
in Unicode 16 lower-case differently. `casefold()` is deliberately not used: it has no SQL twin
("Straße" would match "STRASSE" in Python only). Descriptions arrive stripped by the API anyway, so
trimming only matters for rows written by other means (seed, scripts).
"""

import uuid
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from typing import Protocol

type SeriesKey = tuple[uuid.UUID, str, str | None]


class CareEvent(Protocol):
    id: uuid.UUID
    pet_id: uuid.UUID
    type: str
    description: str | None
    occurred_on: date
    next_due_on: date | None
    created_at: datetime


def normalize_description(description: str | None) -> str | None:
    """Series part of the description: spaces trimmed, lower case. None stays None."""
    return None if description is None else description.strip(" ").lower()


def series_key(type_: str, description: str | None) -> tuple[str, str | None]:
    """Events with the same key (on the same pet) are the same recurring care."""
    return type_, normalize_description(description)


def _recency(event: CareEvent) -> tuple[date, datetime, uuid.UUID]:
    return event.occurred_on, event.created_at, event.id


def latest_per_series(events: Iterable[CareEvent]) -> list[CareEvent]:
    """The newest event of each (pet, type, normalized description) series."""
    latest: dict[SeriesKey, CareEvent] = {}
    for event in events:
        key = (event.pet_id, *series_key(event.type, event.description))
        current = latest.get(key)
        if current is None or _recency(event) > _recency(current):
            latest[key] = event
    return list(latest.values())


def active_reminders(events: Iterable[CareEvent], today: date, within: int) -> list[CareEvent]:
    """Reminders due up to `today + within` days, overdue ones included, by due date.

    `events` must be every event of the pets involved: a newer event of a series hides the older one.
    Reminders due on the same day come in no particular order here: the endpoint breaks those ties by
    pet name in pt-BR (an ICU collation, only available in the database), then by id.
    """
    last_day = today + timedelta(days=within)
    reminders = [
        event
        for event in latest_per_series(events)
        if event.next_due_on is not None and event.next_due_on <= last_day
    ]
    return sorted(reminders, key=lambda event: event.next_due_on)


def is_overdue(next_due_on: date, today: date) -> bool:
    """Due before today. Due today is not overdue yet."""
    return next_due_on < today
