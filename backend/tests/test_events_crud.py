"""POST/GET/PATCH/DELETE /api/events/{id}: create, read, partial update, validation and isolation."""

import uuid

import pytest

from app.core import agenda

EVENTS_URL = "/api/events"
NOT_FOUND = "Evento não encontrado."
READ_FIELDS = {
    "id",
    "title",
    "description",
    "location",
    "starts_on",
    "start_time",
    "end_time",
    "recurrence",
    "repeat_until",
    "created_at",
    "updated_at",
}


def event_url(event_id) -> str:
    return f"{EVENTS_URL}/{event_id}"


def messages(response) -> list[str]:
    detail = response.json()["detail"]
    return [detail] if isinstance(detail, str) else [error["msg"] for error in detail]


@pytest.fixture
def ana(authenticate):
    return authenticate("ana@example.test")


@pytest.fixture
def bia(authenticate):
    return authenticate("bia@example.test")


@pytest.fixture
def make(client, ana):
    def _make(**payload) -> dict:
        payload.setdefault("title", "Consulta")
        payload.setdefault("starts_on", "2026-11-10")
        response = client.post(EVENTS_URL, json=payload, headers=ana[1])
        assert response.status_code == 201, response.text
        return response.json()

    return _make


def test_requires_authentication(client):
    assert client.post(EVENTS_URL, json={"title": "X", "starts_on": "2026-11-10"}).status_code == 401


def test_create_with_defaults_and_read_back(client, ana):
    response = client.post(
        EVENTS_URL,
        json={"title": "  Dentista  ", "starts_on": "2026-11-10", "description": " ", "location": " "},
        headers=ana[1],
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == READ_FIELDS
    assert (body["title"], body["description"], body["location"]) == ("Dentista", None, None)
    assert (body["start_time"], body["end_time"], body["recurrence"], body["repeat_until"]) == (
        None,
        None,
        "none",
        None,
    )
    assert client.get(event_url(body["id"]), headers=ana[1]).json() == body


def test_create_recurring_with_times(make):
    body = make(
        title="Aula de inglês",
        location="Escola",
        start_time="19:00",
        end_time="20:30",
        recurrence="weekly",
        repeat_until="2026-12-15",
    )

    assert (body["start_time"], body["end_time"]) == ("19:00:00", "20:30:00")
    assert (body["recurrence"], body["repeat_until"], body["location"]) == ("weekly", "2026-12-15", "Escola")


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"title": "  "}, "Informe o título."),
        ({"title": "x" * 201}, "O título deve ter no máximo 200 caracteres."),
        ({"location": "x" * 201}, "O local deve ter no máximo 200 caracteres."),
        ({"description": "x" * 5001}, "A descrição deve ter no máximo 5000 caracteres."),
        ({"starts_on": "10/11/2026"}, "Informe uma data válida no formato AAAA-MM-DD."),
        ({"start_time": "7h"}, "Informe um horário válido no formato HH:MM ou HH:MM:SS."),
        ({"end_time": "10:00"}, agenda.END_TIME_WITHOUT_START),
        ({"start_time": "10:00", "end_time": "09:59"}, agenda.END_TIME_NOT_AFTER_START),
        ({"repeat_until": "2026-12-31"}, agenda.REPEAT_UNTIL_WITHOUT_RECURRENCE),
        ({"recurrence": "monthly", "repeat_until": "2026-11-09"}, agenda.REPEAT_UNTIL_BEFORE_START),
        ({"recurrence": "daily"}, "Valor inválido. Use um destes: 'none', 'weekly', 'monthly' ou 'yearly'."),
        ({"recurrence": None}, "Este campo não pode ser nulo."),
        ({"user_id": str(uuid.uuid4())}, "Campo não permitido."),
    ],
)
def test_create_validation_is_422_without_echoing_the_input(client, ana, payload, message):
    body = {"title": "Consulta", "starts_on": "2026-11-10", **payload}

    response = client.post(EVENTS_URL, json=body, headers=ana[1])

    assert response.status_code == 422
    assert messages(response) == [message]


def test_patch_changes_only_the_fields_sent(client, ana, make):
    event = make(start_time="09:00", end_time="10:00", description="Levar exames")

    response = client.patch(
        event_url(event["id"]), json={"title": "Retorno", "end_time": None}, headers=ana[1]
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["title"], body["end_time"], body["start_time"]) == ("Retorno", None, "09:00:00")
    assert body["description"] == "Levar exames"


@pytest.mark.parametrize(
    ("initial", "patch", "message"),
    [
        # Combined with the stored row: the new end time is before the stored start time.
        ({"start_time": "10:00"}, {"end_time": "09:00"}, agenda.END_TIME_NOT_AFTER_START),
        ({"start_time": "10:00", "end_time": "11:00"}, {"start_time": None}, agenda.END_TIME_WITHOUT_START),
        # Turning the repetition off with a repeat_until stored: explicit 422, nothing is cleared silently.
        (
            {"recurrence": "weekly", "repeat_until": "2026-12-01"},
            {"recurrence": "none"},
            agenda.REPEAT_UNTIL_WITHOUT_RECURRENCE,
        ),
        (
            {"recurrence": "weekly", "repeat_until": "2026-12-01"},
            {"starts_on": "2026-12-02"},
            agenda.REPEAT_UNTIL_BEFORE_START,
        ),
        ({}, {"title": None}, "Este campo não pode ser nulo."),
    ],
)
def test_patch_checks_the_combined_state(client, ana, make, initial, patch, message):
    event = make(**initial)

    response = client.patch(event_url(event["id"]), json=patch, headers=ana[1])

    assert response.status_code == 422
    assert messages(response) == [message]
    assert client.get(event_url(event["id"]), headers=ana[1]).json() == event


def test_patch_turns_repetition_off_when_repeat_until_is_cleared_too(client, ana, make):
    event = make(recurrence="monthly", repeat_until="2027-01-10")

    response = client.patch(
        event_url(event["id"]), json={"recurrence": "none", "repeat_until": None}, headers=ana[1]
    )

    assert response.status_code == 200
    assert (response.json()["recurrence"], response.json()["repeat_until"]) == ("none", None)


def test_patch_without_changes_keeps_updated_at(client, ana, make):
    event = make()

    response = client.patch(event_url(event["id"]), json={"title": "Consulta"}, headers=ana[1])

    assert response.json()["updated_at"] == event["updated_at"]


def test_delete(client, ana, make):
    event = make()

    assert client.delete(event_url(event["id"]), headers=ana[1]).status_code == 204
    assert client.get(event_url(event["id"]), headers=ana[1]).status_code == 404


@pytest.mark.parametrize(
    ("method", "body"), [("get", None), ("patch", {"title": "Invasão"}), ("delete", None)]
)
def test_another_users_event_is_404(client, bia, make, method, body):
    event = make()
    kwargs = {"json": body} if body is not None else {}

    response = client.request(method.upper(), event_url(event["id"]), headers=bia[1], **kwargs)

    assert response.status_code == 404
    assert response.json() == {"detail": NOT_FOUND}
