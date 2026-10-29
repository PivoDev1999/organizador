from datetime import date, datetime, timedelta

from backuptool.retention import backups_to_keep


def at(day: date, hour: int = 3, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute)


def daily_backups(first: date, last: date) -> list[datetime]:
    return [at(first + timedelta(days=n)) for n in range((last - first).days + 1)]


def test_month_rollover_keeps_7_daily_4_weekly_6_monthly():
    # Monday, 2026-11-02: one backup a day since 2026-04-01 (more than 6 months).
    today = date(2026, 11, 2)
    backups = daily_backups(date(2026, 4, 1), today)

    kept = {b.date() for b in backups_to_keep(backups, today)}

    daily = {date(2026, 10, 27) + timedelta(days=n) for n in range(7)}  # 27/10 .. 02/11
    # Last backup of the ISO weeks ending on Sunday 01/11, 25/10 and 18/10 (the current week is today's).
    weekly = {date(2026, 11, 1), date(2026, 10, 25), date(2026, 10, 18)}
    # Last day of October, September, August, July and June (November is today's).
    monthly = {date(2026, 10, 31), date(2026, 9, 30), date(2026, 8, 31), date(2026, 7, 31), date(2026, 6, 30)}
    assert kept == daily | weekly | monthly
    assert date(2026, 5, 31) not in kept  # 7th month back: gone


def test_partial_week_and_gaps_keep_the_last_backup_of_each_week():
    # Wednesday, 2026-10-28. The current week only has Monday..Wednesday; the server was off for days.
    today = date(2026, 10, 28)
    backups = [
        at(date(2026, 10, 1)),  # week 28/09..04/10 is too old, and October's last backup is today's
        at(date(2026, 10, 6)),  # Tuesday of 05..11/10, the 4th week back
        at(date(2026, 10, 7)),  # Wednesday, same week: wins over Tuesday
        at(date(2026, 10, 13)),  # the only backup of 12..18/10
        at(date(2026, 10, 20)),
        at(date(2026, 10, 21)),  # last of 19..25/10 (outside the 7 days, which start on 22/10)
        at(date(2026, 10, 26)),
        at(date(2026, 10, 28)),
    ]

    kept = {b.date() for b in backups_to_keep(backups, today)}

    assert kept == {
        date(2026, 10, 28),  # daily, weekly (partial current week) and monthly
        date(2026, 10, 26),  # daily
        date(2026, 10, 21),  # weekly 19..25/10
        date(2026, 10, 13),  # weekly 12..18/10
        # Week 05..11/10 is the 4th one back: 07/10 is kept, 06/10 is not.
        date(2026, 10, 7),
    }


def test_fewer_backups_than_the_retention_keeps_all_and_never_the_newest_alone():
    today = date(2026, 10, 28)
    recent = [at(date(2026, 10, 26)), at(date(2026, 10, 27)), at(today)]
    assert backups_to_keep(recent, today) == set(recent)

    # The server was off for a year: the only backup is outside every window, but it is the newest.
    old = [at(date(2025, 1, 10))]
    assert backups_to_keep(old, today) == set(old)
    assert backups_to_keep([], today) == set()


def test_several_backups_on_the_same_day_keep_the_last_one():
    today = date(2026, 10, 28)
    scheduled_yesterday = at(date(2026, 10, 27), 3)
    manual_yesterday = at(date(2026, 10, 27), 18, 45)
    scheduled_today = at(today, 3)
    manual_today = at(today, 10, 30)

    kept = backups_to_keep([manual_today, scheduled_yesterday, scheduled_today, manual_yesterday], today)

    assert kept == {manual_yesterday, manual_today}
