"""GET /api/events?from=&to=&q=: occurrences in a range, expanded from the recurrence rule."""

from datetime import date, time

import pytest

from app.core import agenda
from app.models import Event

EVENTS_URL = "/api/events"


@pytest.fixture
def ana(authenticate):
    return authenticate("ana@example.test")


@pytest.fixture
def bia(authenticate):
    return authenticate("bia@example.test")


@pytest.fixture
def add(db_session):
    def _add(user, title: str, starts_on: str, **fields) -> Event:
        event = Event(user_id=user.id, title=title, starts_on=date.fromisoformat(starts_on), **fields)
        db_session.add(event)
        db_session.commit()
        return event

    return _add


@pytest.fixture
def listing(client):
    def _list(headers, date_from: str, date_to: str, **params) -> list[tuple[str, str]]:
        response = client.get(
            EVENTS_URL, params={"from": date_from, "to": date_to, **params}, headers=headers
        )
        assert response.status_code == 200, response.text
        return [(item["date"], item["event"]["title"]) for item in response.json()]

    return _list


def test_lists_occurrences_in_the_range_by_date_all_day_first_then_time_and_title(ana, add, listing):
    user, headers = ana
    add(user, "Feira", "2026-10-03", recurrence="weekly")  # Saturdays, started before the range
    add(user, "Aluguel", "2026-01-31", recurrence="monthly")  # 30/11
    add(user, "Dentista", "2026-11-14", start_time=time(14, 0), end_time=time(15, 0))
    add(user, "academia", "2026-11-14", start_time=time(7, 0))
    add(user, "Café", "2026-11-14", start_time=time(7, 0))
    add(user, "Aniversário", "1990-11-21", recurrence="yearly")
    add(user, "Curso", "2026-11-01", recurrence="weekly", repeat_until=date(2026, 11, 8))  # ended
    add(user, "Antes", "2026-11-13")
    add(user, "Depois", "2026-12-01")

    result = listing(headers, "2026-11-14", "2026-11-30")

    assert result == [
        ("2026-11-14", "Feira"),
        ("2026-11-14", "academia"),  # pt-BR order: case does not push it after "Café"
        ("2026-11-14", "Café"),
        ("2026-11-14", "Dentista"),
        ("2026-11-21", "Aniversário"),
        ("2026-11-21", "Feira"),
        ("2026-11-28", "Feira"),
        ("2026-11-30", "Aluguel"),
    ]


def test_occurrence_carries_the_whole_event(client, ana, add):
    user, headers = ana
    event = add(user, "Feira", "2026-11-07", recurrence="weekly", location="Praça")

    response = client.get(EVENTS_URL, params={"from": "2026-11-14", "to": "2026-11-14"}, headers=headers)

    [item] = response.json()
    assert item["date"] == "2026-11-14"
    assert (item["event"]["id"], item["event"]["starts_on"], item["event"]["location"]) == (
        str(event.id),
        "2026-11-07",
        "Praça",
    )


@pytest.mark.parametrize(
    ("q", "expected"),
    [
        ("VACINA", ["Vacina da Mel"]),  # title, any case
        ("carteirinha", ["Vacina da Mel"]),  # description
        ("clínica", ["Vacina da Mel", "Retorno"]),  # location
        ("100%", ["Reunião 100% online"]),  # wildcards match literally
        ("nada", []),
    ],
)
def test_search_in_title_description_and_location(ana, add, listing, q, expected):
    user, headers = ana
    add(user, "Vacina da Mel", "2026-11-10", description="Levar a carteirinha", location="Clínica Pet")
    add(user, "Reunião 100% online", "2026-11-11")
    add(user, "Reunião presencial", "2026-11-12", description="Sala 1")
    add(user, "Retorno", "2026-11-13", location="Clínica Pet")

    assert [title for _, title in listing(headers, "2026-11-01", "2026-11-30", q=q)] == expected


def test_other_users_events_never_show_up(ana, bia, add, listing):
    add(bia[0], "Da Bia", "2026-11-10", recurrence="weekly")

    assert listing(ana[1], "2026-11-01", "2026-11-30") == []


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"to": "2026-11-30"}, "Campo obrigatório."),
        ({"from": "2026-11-30", "to": "2026-11-01"}, agenda.RANGE_REVERSED),
        ({"from": "2026-01-01", "to": "2027-01-02"}, agenda.RANGE_TOO_LONG),
        ({"from": "2026-11-01", "to": "30/11/2026"}, "Informe uma data válida no formato AAAA-MM-DD."),
    ],
)
def test_invalid_range_is_422(client, ana, params, message):
    response = client.get(EVENTS_URL, params=params, headers=ana[1])

    assert response.status_code == 422
    assert [error["msg"] for error in response.json()["detail"]] == [message]
