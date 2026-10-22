from datetime import UTC, date, datetime, time
from types import SimpleNamespace

import pytest

from app.core import clock
from app.core.schedule import day_of_week, is_due

ROUTINES_URL = "/api/routines"
TODAY_URL = f"{ROUTINES_URL}/today"


def routine(frequency="daily", days_of_week=None, day_of_month=None, is_active=True):
    return SimpleNamespace(
        frequency=frequency, days_of_week=days_of_week, day_of_month=day_of_month, is_active=is_active
    )


# --- pure rule ---------------------------------------------------------------------------------


def test_day_of_week_matches_postgres_dow():
    assert day_of_week(date(2026, 10, 18)) == 0  # Sunday
    assert day_of_week(date(2026, 10, 21)) == 3  # Wednesday
    assert day_of_week(date(2026, 10, 24)) == 6  # Saturday


@pytest.mark.parametrize(
    ("schedule", "day", "expected"),
    [
        (routine(), date(2026, 10, 21), True),
        (routine(is_active=False), date(2026, 10, 21), False),
        (routine("weekly", days_of_week=[3]), date(2026, 10, 21), True),
        (routine("weekly", days_of_week=[0, 6]), date(2026, 10, 21), False),
        (routine("monthly", day_of_month=15), date(2026, 10, 15), True),
        (routine("monthly", day_of_month=15), date(2026, 10, 16), False),
        (routine("monthly", day_of_month=31), date(2026, 4, 30), True),
        (routine("monthly", day_of_month=31), date(2026, 4, 29), False),
        (routine("monthly", day_of_month=30), date(2026, 4, 30), True),
        (routine("monthly", day_of_month=31), date(2026, 10, 30), False),
        (routine("monthly", day_of_month=31), date(2026, 10, 31), True),
        (routine("monthly", day_of_month=31), date(2027, 2, 28), True),
        (routine("monthly", day_of_month=29), date(2027, 2, 28), True),
        (routine("monthly", day_of_month=31), date(2028, 2, 28), False),
        (routine("monthly", day_of_month=31), date(2028, 2, 29), True),
        (routine("monthly", day_of_month=29), date(2028, 2, 29), True),
        (routine("monthly", day_of_month=28), date(2028, 2, 29), False),
    ],
)
def test_is_due(schedule, day, expected):
    assert is_due(schedule, day) is expected


# --- GET /today --------------------------------------------------------------------------------


@pytest.fixture
def headers(authenticate):
    return authenticate("ana@example.test")[1]


@pytest.fixture
def freeze_today(monkeypatch):
    def _freeze(day: date) -> None:
        # 15:00 UTC is midday in America/Sao_Paulo: the same calendar day.
        moment = datetime.combine(day, time(15, 0), tzinfo=UTC)
        monkeypatch.setattr(clock, "now_utc", lambda: moment)

    return _freeze


@pytest.fixture
def make(client, headers):
    def _make(name: str, **payload) -> dict:
        payload.setdefault("frequency", "daily")
        response = client.post(ROUTINES_URL, json={"name": name, **payload}, headers=headers)
        assert response.status_code == 201, response.text
        return response.json()

    return _make


def today_names(client, headers) -> list[str]:
    response = client.get(TODAY_URL, headers=headers)
    assert response.status_code == 200, response.text
    return [item["name"] for item in response.json()]


def test_today_lists_due_routines_ordered_by_time(client, headers, make, freeze_today):
    freeze_today(date(2026, 10, 21))  # Wednesday
    make("Sem horário")
    make("Noite", time_of_day="21:00")
    make("Manhã", time_of_day="07:00")
    make("Quarta", frequency="weekly", days_of_week=[3], time_of_day="07:00")
    make("Fim de semana", frequency="weekly", days_of_week=[0, 6])
    make("Dia 21", frequency="monthly", day_of_month=21)
    make("Dia 15", frequency="monthly", day_of_month=15)
    make("Inativa", is_active=False)

    assert today_names(client, headers) == ["Manhã", "Quarta", "Noite", "Dia 21", "Sem horário"]


def test_today_item_has_done_today(client, headers, make, freeze_today):
    freeze_today(date(2026, 10, 21))
    done = make("Feita")
    make("Pendente")
    client.post(f"{ROUTINES_URL}/{done['id']}/logs", json={}, headers=headers)
    # A log on another day does not count.
    pending = client.get(ROUTINES_URL, params={"q": "Pendente"}, headers=headers).json()["items"][0]
    client.post(f"{ROUTINES_URL}/{pending['id']}/logs", json={"done_on": "2026-10-20"}, headers=headers)

    items = client.get(TODAY_URL, headers=headers).json()

    assert {item["name"]: item["done_today"] for item in items} == {"Feita": True, "Pendente": False}
    assert set(items[0]) == {*done, "done_today"}


@pytest.mark.parametrize(
    ("today", "day_of_month", "due"),
    [
        (date(2026, 10, 15), 15, True),
        (date(2026, 4, 30), 31, True),
        (date(2026, 4, 29), 31, False),
        (date(2027, 2, 28), 31, True),
        (date(2028, 2, 28), 31, False),
        (date(2028, 2, 29), 31, True),
        (date(2028, 2, 29), 29, True),
    ],
)
def test_today_monthly(client, headers, make, freeze_today, today, day_of_month, due):
    freeze_today(today)
    make("Mensal", frequency="monthly", day_of_month=day_of_month)

    assert today_names(client, headers) == (["Mensal"] if due else [])


def test_today_uses_app_timezone(client, headers, make, monkeypatch):
    # 02:00 UTC on Thursday is still Wednesday 23:00 in America/Sao_Paulo.
    monkeypatch.setattr(clock, "now_utc", lambda: datetime(2026, 10, 22, 2, 0, tzinfo=UTC))
    make("Quarta", frequency="weekly", days_of_week=[3])

    assert today_names(client, headers) == ["Quarta"]
