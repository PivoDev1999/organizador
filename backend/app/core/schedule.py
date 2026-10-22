"""Pure scheduling rules of routines: no database, no clock. The reference for SQL and tests alike.

Weekdays follow PostgreSQL's EXTRACT(DOW): 0 = Sunday ... 6 = Saturday. Python's `date.weekday()`
uses 0 = Monday, so always convert with `day_of_week()`.
"""

import calendar
from collections.abc import Sequence
from datetime import date
from typing import Protocol

from app.models.routine import RoutineFrequency

# Fields that each frequency uses to say "when". Daily needs none.
SCHEDULE_FIELDS: dict[str, tuple[str, ...]] = {
    RoutineFrequency.DAILY: (),
    RoutineFrequency.WEEKLY: ("days_of_week",),
    RoutineFrequency.MONTHLY: ("day_of_month",),
}

DAILY_EXTRA = "Rotinas diárias não usam dias da semana (days_of_week) nem dia do mês (day_of_month)."
WEEKLY_MISSING_DAYS = "Informe os dias da semana (days_of_week) para rotinas semanais."
WEEKLY_EXTRA = "Rotinas semanais não usam dia do mês (day_of_month)."
MONTHLY_MISSING_DAY = "Informe o dia do mês (day_of_month) para rotinas mensais."
MONTHLY_EXTRA = "Rotinas mensais não usam dias da semana (days_of_week)."


class Schedule(Protocol):
    frequency: str
    days_of_week: list[int] | None
    day_of_month: int | None
    is_active: bool


def schedule_problem(
    frequency: str, days_of_week: Sequence[int] | None, day_of_month: int | None
) -> str | None:
    """Portuguese message if the fields do not match the frequency, else None.

    Mirrors the `schedule_matches_frequency` CHECK, so a bad combination is a clear 422 and never an
    integrity error. An empty list counts as missing (the CHECK requires cardinality > 0).
    """
    has_days = bool(days_of_week)
    has_day_of_month = day_of_month is not None
    if frequency == RoutineFrequency.DAILY:
        return DAILY_EXTRA if has_days or has_day_of_month else None
    if frequency == RoutineFrequency.WEEKLY:
        if not has_days:
            return WEEKLY_MISSING_DAYS
        return WEEKLY_EXTRA if has_day_of_month else None
    if frequency == RoutineFrequency.MONTHLY:
        if not has_day_of_month:
            return MONTHLY_MISSING_DAY
        return MONTHLY_EXTRA if has_days else None
    return None  # unknown frequencies are rejected by the enum


def day_of_week(day: date) -> int:
    """0 = Sunday ... 6 = Saturday, like PostgreSQL's EXTRACT(DOW)."""
    return (day.weekday() + 1) % 7


def is_due(routine: Schedule, day: date) -> bool:
    """Whether an active routine is scheduled for `day`.

    Monthly routines whose day does not exist in the month (29-31) fall on its last day: day 31 is due
    on 30/04 and on 28/02 (29/02 in leap years).
    """
    if not routine.is_active:
        return False
    if routine.frequency == RoutineFrequency.DAILY:
        return True
    if routine.frequency == RoutineFrequency.WEEKLY:
        return day_of_week(day) in (routine.days_of_week or ())
    if routine.frequency == RoutineFrequency.MONTHLY and routine.day_of_month is not None:
        last_day = calendar.monthrange(day.year, day.month)[1]
        return routine.day_of_month == day.day or (day.day == last_day and routine.day_of_month > last_day)
    return False
