"""Pure rules of the agenda (events): no database, no clock. The reference for services and tests alike.

A recurring event repeats from `starts_on` until `repeat_until` (inclusive), or forever when it is None:

- weekly: every 7 days from `starts_on`;
- monthly: on the same day of the month; months without that day (29, 30, 31) use their last day, and
  the next month goes back to the original day (31/01 -> 28/02 -> 31/03);
- yearly: on the same day and month; 29/02 falls on 28/02 in non-leap years.

`occurrences` jumps straight to the first occurrence on or after the start of the range, so its cost
depends on the size of the range, never on how old the event is.
"""

import calendar
from datetime import MAXYEAR, date, time

from app.models.event import EventRecurrence

DAYS_PER_WEEK = 7
MONTHS_PER_YEAR = 12
# Longest range of a listing (`from`..`to`, both inclusive): a whole leap year.
RANGE_MAX_DAYS = 366

END_TIME_WITHOUT_START = "Informe o horário de início (start_time) para usar o horário de término (end_time)."
END_TIME_NOT_AFTER_START = (
    "O horário de término (end_time) deve ser depois do horário de início (start_time)."
)
REPEAT_UNTIL_WITHOUT_RECURRENCE = (
    "A data final da repetição (repeat_until) só vale para eventos que se repetem (recurrence diferente "
    "de none)."
)
REPEAT_UNTIL_BEFORE_START = (
    "A data final da repetição (repeat_until) não pode ser anterior à data do evento (starts_on)."
)
RANGE_REVERSED = "A data inicial (from) não pode ser posterior à data final (to)."
RANGE_TOO_LONG = f"O intervalo deve ter no máximo {RANGE_MAX_DAYS} dias."


def event_problem(
    starts_on: date,
    start_time: time | None,
    end_time: time | None,
    recurrence: str,
    repeat_until: date | None,
) -> str | None:
    """Portuguese message if the fields do not fit together, else None.

    Mirrors the CHECKs `end_time_after_start_time` and `repeat_until_matches_recurrence`, so a bad
    combination is a clear 422 and never an integrity error.
    """
    if end_time is not None:
        if start_time is None:
            return END_TIME_WITHOUT_START
        if end_time <= start_time:
            return END_TIME_NOT_AFTER_START
    if repeat_until is not None:
        if recurrence == EventRecurrence.NONE:
            return REPEAT_UNTIL_WITHOUT_RECURRENCE
        if repeat_until < starts_on:
            return REPEAT_UNTIL_BEFORE_START
    return None


def range_problem(date_from: date, date_to: date) -> str | None:
    """Portuguese message if `from`..`to` is not a valid listing range, else None."""
    if date_from > date_to:
        return RANGE_REVERSED
    if (date_to - date_from).days + 1 > RANGE_MAX_DAYS:
        return RANGE_TOO_LONG
    return None


def _clamped(year: int, month: int, day: int) -> date:
    """`day` of that month, or its last day when the month is shorter."""
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def _weekly(starts_on: date, first: date, last: date) -> list[date]:
    # Ordinals avoid building dates past date.max (9999-12-31).
    start = starts_on.toordinal()
    weeks = -(-(first.toordinal() - start) // DAYS_PER_WEEK)  # ceil: first week on or after `first`
    return [
        date.fromordinal(ordinal)
        for ordinal in range(start + weeks * DAYS_PER_WEEK, last.toordinal() + 1, DAYS_PER_WEEK)
    ]


def _monthly(starts_on: date, first: date, last: date) -> list[date]:
    index = (first.year - starts_on.year) * MONTHS_PER_YEAR + first.month - starts_on.month
    result: list[date] = []
    while True:
        year, month = divmod(starts_on.month - 1 + index, MONTHS_PER_YEAR)
        year += starts_on.year
        if year > MAXYEAR:
            return result
        day = _clamped(year, month + 1, starts_on.day)
        if day > last:
            return result
        if day >= first:  # only the month of `first` can fall before it
            result.append(day)
        index += 1


def _yearly(starts_on: date, first: date, last: date) -> list[date]:
    result: list[date] = []
    for year in range(first.year, min(last.year, MAXYEAR) + 1):
        day = _clamped(year, starts_on.month, starts_on.day)
        if first <= day <= last:
            result.append(day)
    return result


def occurrences(
    starts_on: date, recurrence: str, repeat_until: date | None, date_from: date, date_to: date
) -> list[date]:
    """Days the event happens between `date_from` and `date_to` (both inclusive), in order.

    Never before `starts_on` nor after `repeat_until`.
    """
    first = max(date_from, starts_on)
    last = date_to if repeat_until is None else min(date_to, repeat_until)
    if first > last:
        return []
    match recurrence:
        case EventRecurrence.NONE:
            return [starts_on] if first == starts_on else []
        case EventRecurrence.WEEKLY:
            return _weekly(starts_on, first, last)
        case EventRecurrence.MONTHLY:
            return _monthly(starts_on, first, last)
        case EventRecurrence.YEARLY:
            return _yearly(starts_on, first, last)
    raise ValueError("unknown recurrence")
