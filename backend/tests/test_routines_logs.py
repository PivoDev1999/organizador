from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.core import clock
from app.models import RoutineLog

ROUTINES_URL = "/api/routines"
NOW = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)  # 12:00 of 2026-10-21 in America/Sao_Paulo
LOG_FIELDS = {"id", "routine_id", "done_on", "note", "created_at"}


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch):
    monkeypatch.setattr(clock, "now_utc", lambda: NOW)


@pytest.fixture
def ana(authenticate):
    return authenticate("ana@example.test")


@pytest.fixture
def headers(ana):
    return ana[1]


@pytest.fixture
def routine(client, headers):
    response = client.post(ROUTINES_URL, json={"name": "Passear", "frequency": "daily"}, headers=headers)
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def logs_url(routine):
    return f"{ROUTINES_URL}/{routine['id']}/logs"


def test_log_defaults_to_today(client, headers, routine, logs_url, ana, db_session):
    response = client.post(logs_url, headers=headers)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == LOG_FIELDS
    assert body["routine_id"] == routine["id"]
    assert body["done_on"] == "2026-10-21"
    assert body["note"] is None
    stored = db_session.scalar(select(RoutineLog))
    assert stored.user_id == ana[0].id


def test_log_past_day_with_note(client, headers, logs_url):
    response = client.post(logs_url, json={"done_on": "2026-10-01", "note": "  Atrasado  "}, headers=headers)

    assert response.status_code == 201
    assert response.json()["done_on"] == "2026-10-01"
    assert response.json()["note"] == "Atrasado"


def test_log_same_day_twice_is_conflict(client, headers, logs_url):
    assert client.post(logs_url, json={}, headers=headers).status_code == 201

    response = client.post(logs_url, json={"done_on": "2026-10-21"}, headers=headers)

    assert response.status_code == 409
    assert response.json() == {"detail": "Rotina já marcada como feita nesse dia."}


def test_log_in_the_future_is_rejected(client, headers, logs_url):
    response = client.post(logs_url, json={"done_on": "2026-10-22"}, headers=headers)

    assert response.status_code == 422
    assert response.json()["detail"] == [
        {"type": "value_error", "loc": ["body"], "msg": "A data não pode ser no futuro."}
    ]


def test_log_on_inactive_routine_is_conflict(client, headers, routine, logs_url):
    client.patch(f"{ROUTINES_URL}/{routine['id']}", json={"is_active": False}, headers=headers)

    response = client.post(logs_url, json={}, headers=headers)

    assert response.status_code == 409
    assert response.json() == {"detail": "Rotina inativa."}


@pytest.mark.parametrize(
    "body",
    [{"done_on": "21/10/2026"}, {"done_on": "2026-10-21T10:00:00"}, {"user_id": "x"}, {"note": 1}],
)
def test_log_rejects_invalid_body(client, headers, logs_url, body):
    assert client.post(logs_url, json=body, headers=headers).status_code == 422


def test_undo_log(client, headers, logs_url):
    client.post(logs_url, json={}, headers=headers)

    response = client.delete(f"{logs_url}/2026-10-21", headers=headers)

    assert response.status_code == 204
    assert client.get(logs_url, headers=headers).json()["total"] == 0
    # Can be marked again after undoing.
    assert client.post(logs_url, json={}, headers=headers).status_code == 201


def test_undo_missing_log_is_not_found(client, headers, logs_url):
    response = client.delete(f"{logs_url}/2026-10-21", headers=headers)

    assert response.status_code == 404
    assert response.json() == {"detail": "Registro não encontrado."}


def test_undo_rejects_invalid_date(client, headers, logs_url):
    assert client.delete(f"{logs_url}/2026-13-01", headers=headers).status_code == 422


def test_history_newest_first_with_filters(client, headers, logs_url):
    for day in ["2026-10-01", "2026-10-10", "2026-10-15", "2026-10-21"]:
        assert client.post(logs_url, json={"done_on": day}, headers=headers).status_code == 201

    def days(**params) -> list[str]:
        response = client.get(logs_url, params=params, headers=headers)
        assert response.status_code == 200, response.text
        return [item["done_on"] for item in response.json()["items"]]

    assert days() == ["2026-10-21", "2026-10-15", "2026-10-10", "2026-10-01"]
    assert days(**{"from": "2026-10-10", "to": "2026-10-15"}) == ["2026-10-15", "2026-10-10"]
    assert days(**{"from": "2026-10-15"}) == ["2026-10-21", "2026-10-15"]
    assert days(to="2026-10-01") == ["2026-10-01"]
    page = client.get(logs_url, params={"limit": 1, "offset": 1}, headers=headers).json()
    assert page["total"] == 4
    assert [item["done_on"] for item in page["items"]] == ["2026-10-15"]


def test_history_rejects_inverted_range(client, headers, logs_url):
    response = client.get(logs_url, params={"from": "2026-10-15", "to": "2026-10-10"}, headers=headers)

    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == (
        "A data inicial (from) não pode ser posterior à data final (to)."
    )
