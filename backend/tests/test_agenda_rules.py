"""Pure agenda rules (app.core.agenda): recurrence expansion and field combinations."""

from datetime import date, time

import pytest

from app.core import agenda
from app.core.agenda import event_problem, occurrences, range_problem

D = date.fromisoformat


@pytest.mark.parametrize(
    ("starts_on", "recurrence", "repeat_until", "date_from", "date_to", "expected"),
    [
        # One-off: only its own day, and only inside the range.
        ("2026-03-10", "none", None, "2026-03-01", "2026-03-31", ["2026-03-10"]),
        ("2026-03-10", "none", None, "2026-03-11", "2026-03-31", []),
        # Weekly, with a range starting mid-way (and not on an occurrence).
        (
            "2026-01-05",
            "weekly",
            None,
            "2026-03-01",
            "2026-03-20",
            ["2026-03-02", "2026-03-09", "2026-03-16"],
        ),
        # Monthly on the 31st: last day in shorter months, back to the 31st afterwards.
        (
            "2026-01-31",
            "monthly",
            None,
            "2026-01-01",
            "2026-05-31",
            ["2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30", "2026-05-31"],
        ),
        ("2027-12-31", "monthly", None, "2028-02-01", "2028-02-29", ["2028-02-29"]),  # leap February
        ("2026-01-30", "monthly", None, "2026-02-01", "2026-03-31", ["2026-02-28", "2026-03-30"]),
        # Monthly where the occurrence of the first month is before the range.
        ("2026-01-15", "monthly", None, "2026-03-20", "2026-05-01", ["2026-04-15"]),
        # Yearly on 29/02: 28/02 in common years, 29/02 in leap ones.
        (
            "2024-02-29",
            "yearly",
            None,
            "2025-01-01",
            "2028-12-31",
            ["2025-02-28", "2026-02-28", "2027-02-28", "2028-02-29"],
        ),
        ("2020-07-14", "yearly", None, "2026-07-15", "2027-07-13", []),  # range between two occurrences
        # repeat_until is inclusive and caps the series.
        (
            "2026-03-02",
            "weekly",
            "2026-03-16",
            "2026-03-01",
            "2026-04-30",
            ["2026-03-02", "2026-03-09", "2026-03-16"],
        ),
        ("2026-03-02", "weekly", "2026-03-15", "2026-03-16", "2026-04-30", []),
        # Nothing before starts_on.
        ("2026-06-10", "monthly", None, "2026-01-01", "2026-07-31", ["2026-06-10", "2026-07-10"]),
        # Far future: no overflow past 9999-12-31.
        ("2026-01-31", "monthly", None, "9999-12-01", "9999-12-31", ["9999-12-31"]),
        ("2026-01-01", "weekly", None, "9999-12-25", "9999-12-31", ["9999-12-30"]),
    ],
)
def test_occurrences(starts_on, recurrence, repeat_until, date_from, date_to, expected):
    until = D(repeat_until) if repeat_until else None

    result = occurrences(D(starts_on), recurrence, until, D(date_from), D(date_to))

    assert result == [D(value) for value in expected]


def test_occurrences_cost_depends_on_the_range_not_on_the_age_of_the_event():
    # Daily-like work since year 1 would be ~740k iterations; a single-day range must stay instant.
    assert occurrences(date(1, 1, 1), "weekly", None, D("2026-11-02"), D("2026-11-02")) == [D("2026-11-02")]


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({}, None),
        ({"start_time": time(9), "end_time": time(10)}, None),
        ({"end_time": time(10)}, agenda.END_TIME_WITHOUT_START),
        ({"start_time": time(10), "end_time": time(10)}, agenda.END_TIME_NOT_AFTER_START),
        ({"repeat_until": D("2026-12-31")}, agenda.REPEAT_UNTIL_WITHOUT_RECURRENCE),
        ({"recurrence": "weekly", "repeat_until": D("2026-03-09")}, agenda.REPEAT_UNTIL_BEFORE_START),
        ({"recurrence": "weekly", "repeat_until": D("2026-03-10")}, None),
    ],
)
def test_event_problem_mirrors_the_checks(fields, expected):
    values = {"start_time": None, "end_time": None, "recurrence": "none", "repeat_until": None, **fields}

    assert event_problem(D("2026-03-10"), **values) == expected


@pytest.mark.parametrize(
    ("date_from", "date_to", "expected"),
    [
        ("2028-01-01", "2028-12-31", None),  # 366 days
        ("2026-01-01", "2027-01-01", None),  # 366 days, both ends counted
        ("2026-01-01", "2027-01-02", agenda.RANGE_TOO_LONG),  # 367 days
        ("2026-01-02", "2026-01-01", agenda.RANGE_REVERSED),
    ],
)
def test_range_problem(date_from, date_to, expected):
    assert range_problem(D(date_from), D(date_to)) == expected
