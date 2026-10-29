"""GFS retention of the daily backups: 7 daily + 4 weekly + 6 monthly.

A pure function (no clock, no file system) so the rule is unit tested on its own (tests/test_retention.py).

Every window is counted in calendar periods ending at `today`, in the APP_TIMEZONE local time of the
backup names:
- daily: the last backup of each of the 7 days `today - 6 .. today`;
- weekly: the last backup of each of the 4 ISO weeks (Monday to Sunday) ending at the current one, which
  may be partial;
- monthly: the last backup of each of the 6 calendar months ending at the current one.

A backup kept by more than one rule counts once. The newest backup is always kept, even when it falls
outside every window (the server was off for months): retention never leaves the folder empty.
"""

from collections.abc import Callable, Hashable, Iterable
from datetime import date, datetime, timedelta

DAILY = 7
WEEKLY = 4
MONTHLY = 6


def _week(day: date) -> tuple[int, int]:
    iso = day.isocalendar()
    return iso.year, iso.week


def _month(day: date) -> tuple[int, int]:
    return day.year, day.month


def _last_of_each(backups: list[datetime], period: Callable[[date], Hashable], periods: set) -> set[datetime]:
    """The newest backup of each period in `periods` (backups sorted from oldest to newest)."""
    latest: dict[Hashable, datetime] = {}
    for backup in backups:
        key = period(backup.date())
        if key in periods:
            latest[key] = backup  # sorted: the last one written wins
    return set(latest.values())


def backups_to_keep(
    backups: Iterable[datetime],
    today: date,
    *,
    daily: int = DAILY,
    weekly: int = WEEKLY,
    monthly: int = MONTHLY,
) -> set[datetime]:
    """Which of `backups` (local date and time of each one) to keep on `today`; delete the others."""
    ordered = sorted(set(backups))
    if not ordered:
        return set()

    days = {today - timedelta(days=offset) for offset in range(daily)}
    weeks = {_week(today - timedelta(weeks=offset)) for offset in range(weekly)}
    months: set[tuple[int, int]] = set()
    year, month = today.year, today.month
    for _ in range(monthly):
        months.add((year, month))
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)

    keep = _last_of_each(ordered, lambda day: day, days)
    keep |= _last_of_each(ordered, _week, weeks)
    keep |= _last_of_each(ordered, _month, months)
    # Backups "after today" (clock changed, time zone moved) are never deleted by this rule.
    keep |= {backup for backup in ordered if backup.date() > today}
    keep.add(ordered[-1])
    return keep
