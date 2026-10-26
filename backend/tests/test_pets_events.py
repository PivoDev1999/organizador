import uuid
from datetime import UTC, datetime

import pytest

from app.core import clock

PETS_URL = "/api/pets"
NOW = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)  # 12:00 of 2026-10-21 in America/Sao_Paulo
EVENT_FIELDS = {
    "id",
    "pet_id",
    "type",
    "occurred_on",
    "next_due_on",
    "description",
    "created_at",
    "updated_at",
}
NEXT_BEFORE = "A próxima data não pode ser anterior à data do evento."
FUTURE = "A data do evento não pode ser no futuro."


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch):
    monkeypatch.setattr(clock, "now_utc", lambda: NOW)


@pytest.fixture
def headers(authenticate):
    return authenticate("ana@example.test")[1]


@pytest.fixture
def make_pet(client, headers):
    def _make(name: str = "Mel") -> dict:
        response = client.post(PETS_URL, json={"name": name, "species": "Cachorro"}, headers=headers)
        assert response.status_code == 201, response.text
        return response.json()

    return _make


@pytest.fixture
def pet(make_pet):
    return make_pet()


@pytest.fixture
def events_url(pet):
    return f"{PETS_URL}/{pet['id']}/events"


@pytest.fixture
def make_event(client, headers, events_url):
    def _make(**payload) -> dict:
        payload.setdefault("type", "vaccine")
        payload.setdefault("occurred_on", "2026-10-01")
        response = client.post(events_url, json=payload, headers=headers)
        assert response.status_code == 201, response.text
        return response.json()

    return _make


def body_messages(response) -> list[str]:
    return [error["msg"] for error in response.json()["detail"]]


def test_create_event_and_read_back(client, headers, pet, events_url):
    payload = {
        "type": "vaccine",
        "occurred_on": "2026-10-21",
        "next_due_on": "2027-10-21",
        "description": " V10 ",
    }

    response = client.post(events_url, json=payload, headers=headers)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == EVENT_FIELDS
    assert (body["pet_id"], body["type"], body["description"]) == (pet["id"], "vaccine", "V10")
    assert (body["occurred_on"], body["next_due_on"]) == ("2026-10-21", "2027-10-21")
    assert client.get(events_url, headers=headers).json()["items"] == [body]


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"occurred_on": "2026-10-22"}, FUTURE),
        ({"occurred_on": "2026-10-10", "next_due_on": "2026-10-09"}, NEXT_BEFORE),
        (
            {"type": "bath"},
            "Valor inválido. Use um destes: 'vaccine', 'vet', 'medication', 'grooming' ou 'other'.",
        ),
        ({"occurred_on": None}, "Este campo não pode ser nulo."),
        ({"description": "x" * 1001}, "A descrição deve ter no máximo 1000 caracteres."),
        ({"pet_id": str(uuid.uuid4())}, "Campo não permitido."),
    ],
)
def test_create_rejects_invalid_event(client, headers, events_url, payload, message):
    response = client.post(
        events_url, json={"type": "vet", "occurred_on": "2026-10-01", **payload}, headers=headers
    )

    assert response.status_code == 422
    assert body_messages(response) == [message]
    assert client.get(events_url, headers=headers).json()["total"] == 0


@pytest.mark.parametrize(
    ("patch", "message"),
    [
        # Combined state: stored next_due_on is 2026-10-31.
        ({"occurred_on": "2026-11-01"}, FUTURE),
        ({"occurred_on": "2026-10-20", "next_due_on": None, "type": None}, "Este campo não pode ser nulo."),
        ({"next_due_on": "2026-09-30"}, NEXT_BEFORE),
    ],
)
def test_patch_rejects_invalid_changes_and_keeps_the_event(
    client, headers, events_url, make_event, patch, message
):
    event = make_event(next_due_on="2026-10-31")

    response = client.patch(f"{events_url}/{event['id']}", json=patch, headers=headers)

    assert response.status_code == 422
    assert body_messages(response) == [message]
    assert client.get(events_url, headers=headers).json()["items"] == [event]


def test_patch_moving_occurred_on_past_the_stored_next_date_is_rejected(
    client, headers, events_url, make_event
):
    event = make_event(occurred_on="2026-09-01", next_due_on="2026-10-01")

    response = client.patch(
        f"{events_url}/{event['id']}", json={"occurred_on": "2026-10-02"}, headers=headers
    )

    assert response.status_code == 422
    assert body_messages(response) == [NEXT_BEFORE]


def test_patch_updates_and_noop_keeps_updated_at(client, headers, events_url, make_event):
    event = make_event(description="V10", next_due_on="2027-10-01")
    url = f"{events_url}/{event['id']}"

    assert client.patch(url, json={"description": "V10", "type": "vaccine"}, headers=headers).json() == event
    response = client.patch(
        url, json={"type": "medication", "next_due_on": None, "description": ""}, headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["type"], body["next_due_on"], body["description"]) == ("medication", None, None)


def test_delete_event(client, headers, events_url, make_event):
    event = make_event()

    assert client.delete(f"{events_url}/{event['id']}", headers=headers).status_code == 204
    assert client.get(events_url, headers=headers).json()["total"] == 0
    assert client.delete(f"{events_url}/{event['id']}", headers=headers).json() == {
        "detail": "Evento não encontrado."
    }


@pytest.mark.parametrize("method", ["PATCH", "DELETE"])
def test_event_of_another_pet_or_user_is_not_found(
    client, headers, authenticate, make_pet, make_event, method
):
    event = make_event()
    other_pet = make_pet("Bidu")
    _, bia_headers = authenticate("bia@example.test")
    bia_pet = client.post(PETS_URL, json={"name": "Rex", "species": "Cão"}, headers=bia_headers).json()
    body = {"description": "Invasão"} if method == "PATCH" else None

    via_other_pet = client.request(
        method, f"{PETS_URL}/{other_pet['id']}/events/{event['id']}", json=body, headers=headers
    )
    via_bia_pet = client.request(
        method, f"{PETS_URL}/{bia_pet['id']}/events/{event['id']}", json=body, headers=bia_headers
    )
    via_ana_pet = client.request(
        method, f"{PETS_URL}/{event['pet_id']}/events/{event['id']}", json=body, headers=bia_headers
    )

    assert (via_other_pet.status_code, via_other_pet.json()) == (404, {"detail": "Evento não encontrado."})
    assert (via_bia_pet.status_code, via_bia_pet.json()) == (404, {"detail": "Evento não encontrado."})
    assert (via_ana_pet.status_code, via_ana_pet.json()) == (404, {"detail": "Pet não encontrado."})


def test_history_newest_first_with_filters(client, headers, events_url, make_event):
    make_event(type="vet", occurred_on="2026-09-01")
    make_event(type="vaccine", occurred_on="2026-10-10")
    make_event(type="grooming", occurred_on="2026-10-15")
    make_event(type="vaccine", occurred_on="2026-10-21")

    def listed(**params) -> list[tuple[str, str]]:
        response = client.get(events_url, params=params, headers=headers)
        assert response.status_code == 200, response.text
        return [(item["occurred_on"], item["type"]) for item in response.json()["items"]]

    assert [day for day, _ in listed()] == ["2026-10-21", "2026-10-15", "2026-10-10", "2026-09-01"]
    assert listed(type=["vaccine", "vet"], **{"from": "2026-10-10"}) == [
        ("2026-10-21", "vaccine"),
        ("2026-10-10", "vaccine"),
    ]
    assert listed(**{"from": "2026-10-10", "to": "2026-10-15"}) == [
        ("2026-10-15", "grooming"),
        ("2026-10-10", "vaccine"),
    ]
    page = client.get(events_url, params={"limit": 1, "offset": 3}, headers=headers).json()
    assert (page["total"], [item["occurred_on"] for item in page["items"]]) == (4, ["2026-09-01"])


def test_history_rejects_inverted_range(client, headers, events_url):
    response = client.get(events_url, params={"from": "2026-10-15", "to": "2026-10-10"}, headers=headers)

    assert response.status_code == 422
    assert body_messages(response) == ["A data inicial (from) não pode ser posterior à data final (to)."]
