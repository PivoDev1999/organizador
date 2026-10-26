import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core import clock
from app.models import PetEvent, Transaction

PETS_URL = "/api/pets"
NOT_FOUND = "Pet não encontrado."
NOW = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)  # 12:00 of 2026-10-21 in America/Sao_Paulo
READ_FIELDS = {
    "id",
    "name",
    "species",
    "breed",
    "birth_date",
    "weight_kg",
    "notes",
    "created_at",
    "updated_at",
}


def pet_url(pet_id) -> str:
    return f"{PETS_URL}/{pet_id}"


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
def bia(authenticate):
    return authenticate("bia@example.test")


@pytest.fixture
def make(client, headers):
    def _make(name: str = "Mel", **payload) -> dict:
        payload.setdefault("species", "Cachorro")
        response = client.post(PETS_URL, json={"name": name, **payload}, headers=headers)
        assert response.status_code == 201, response.text
        return response.json()

    return _make


def messages(response) -> list[str]:
    return [error["msg"] for error in response.json()["detail"]]


# --- create ------------------------------------------------------------------------------------


def test_create_normalizes_and_reads_back(client, headers):
    payload = {
        "name": "  Mel  ",
        "species": " Cachorro ",
        "breed": "   ",
        "birth_date": "2022-03-12",
        "weight_kg": 14.3,
        "notes": " Alérgica a frango. ",
    }

    response = client.post(PETS_URL, json=payload, headers=headers)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == READ_FIELDS
    assert (body["name"], body["species"], body["breed"]) == ("Mel", "Cachorro", None)
    assert (body["birth_date"], body["weight_kg"], body["notes"]) == (
        "2022-03-12",
        "14.30",
        "Alérgica a frango.",
    )
    assert client.get(pet_url(body["id"]), headers=headers).json() == body


def test_weight_is_serialized_with_two_places(make):
    assert make(weight_kg="12.5")["weight_kg"] == "12.50"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"weight_kg": "0"}, "O valor deve ser maior que 0."),
        ({"weight_kg": -1}, "O valor deve ser maior que 0."),
        ({"weight_kg": "1.005"}, "Use no máximo 2 casas decimais."),
        ({"weight_kg": "1000"}, "O valor deve ser no máximo 999.99."),
        ({"name": "   "}, "Informe o nome."),
        ({"species": ""}, "Informe a espécie."),
        ({"user_id": str(uuid.uuid4())}, "Campo não permitido."),
    ],
)
def test_create_rejects_invalid_fields(client, headers, payload, message):
    response = client.post(PETS_URL, json={"name": "Mel", "species": "Cachorro", **payload}, headers=headers)

    assert response.status_code == 422
    assert messages(response) == [message]
    assert client.get(PETS_URL, headers=headers).json()["total"] == 0


@pytest.mark.parametrize(
    ("now", "birth_date", "status"),
    [
        (NOW, "2026-10-21", 201),
        (NOW, "2026-10-22", 422),
        # 02:59 UTC of the 22nd is still 23:59 of the 21st in São Paulo.
        (datetime(2026, 10, 22, 2, 59, tzinfo=UTC), "2026-10-22", 422),
        (datetime(2026, 10, 22, 3, 0, tzinfo=UTC), "2026-10-22", 201),
    ],
)
def test_birth_date_cannot_be_in_the_future(client, headers, monkeypatch, now, birth_date, status):
    monkeypatch.setattr(clock, "now_utc", lambda: now)

    response = client.post(
        PETS_URL, json={"name": "Mel", "species": "Cachorro", "birth_date": birth_date}, headers=headers
    )

    assert response.status_code == status
    if status == 422:
        assert response.json()["detail"] == [
            {"type": "value_error", "loc": ["body"], "msg": "A data de nascimento não pode ser no futuro."}
        ]


def test_validation_message_does_not_echo_input(client, headers):
    response = client.post(
        PETS_URL, json={"name": "Mel", "species": "Cachorro", "weight_kg": "segredo-123"}, headers=headers
    )

    assert response.status_code == 422
    assert "segredo-123" not in response.text


# --- list ----------------------------------------------------------------------------------------


@pytest.fixture
def pets(make):
    make("Mel")
    make("frajola", species="Gato")
    make("Átila", species="Gato")
    make("Bidu")
    make("100%_off", species="Peixe")


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({}, ["100%_off", "Átila", "Bidu", "frajola", "Mel"]),
        ({"sort": "-name"}, ["Mel", "frajola", "Bidu", "Átila", "100%_off"]),
        ({"species": ["Gato", " Peixe "]}, ["100%_off", "Átila", "frajola"]),
        ({"species": ["  "]}, ["100%_off", "Átila", "Bidu", "frajola", "Mel"]),
        ({"q": "FRA"}, ["frajola"]),
        ({"q": "%_"}, ["100%_off"]),
    ],
)
def test_list_filters_and_sorts(client, headers, pets, params, expected):
    response = client.get(PETS_URL, params=params, headers=headers)

    assert response.status_code == 200, response.text
    assert [pet["name"] for pet in response.json()["items"]] == expected


def test_list_paginates_with_total(client, headers, pets):
    body = client.get(PETS_URL, params={"limit": 2, "offset": 1}, headers=headers).json()

    assert [pet["name"] for pet in body["items"]] == ["Átila", "Bidu"]
    assert (body["total"], body["limit"], body["offset"]) == (5, 2, 1)


@pytest.mark.parametrize("params", [{"sort": "species"}, {"q": "x" * 101}])
def test_list_rejects_invalid_query(client, headers, params):
    assert client.get(PETS_URL, params=params, headers=headers).status_code == 422


def test_species_are_distinct_sorted_and_isolated(client, headers, bia, pets):
    _, bia_headers = bia
    client.post(PETS_URL, json={"name": "Piu", "species": "Ave"}, headers=bia_headers)

    assert client.get(f"{PETS_URL}/species", headers=headers).json() == ["Cachorro", "Gato", "Peixe"]
    assert client.get(f"{PETS_URL}/species", headers=bia_headers).json() == ["Ave"]


# --- update --------------------------------------------------------------------------------------


def test_patch_updates_and_clears_fields(client, headers, make):
    pet = make(breed="SRD", weight_kg="4.8", notes="Arisco", birth_date="2024-08-01")

    response = client.patch(
        pet_url(pet["id"]),
        json={"name": "Frajola", "species": "Gato", "breed": " ", "weight_kg": None, "notes": None},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["name"], body["species"], body["breed"], body["weight_kg"], body["notes"]) == (
        "Frajola",
        "Gato",
        None,
        None,
        None,
    )
    assert body["birth_date"] == "2024-08-01"


@pytest.mark.parametrize(
    "patch",
    [{"species": None}, {"birth_date": "2026-10-22"}, {"weight_kg": 0}],
)
def test_patch_rejects_invalid_changes_and_keeps_the_pet(client, headers, make, patch):
    pet = make()

    response = client.patch(pet_url(pet["id"]), json=patch, headers=headers)

    assert response.status_code == 422
    assert client.get(pet_url(pet["id"]), headers=headers).json() == pet


def test_noop_patch_keeps_updated_at(client, headers, make):
    pet = make(weight_kg="14.3")

    response = client.patch(pet_url(pet["id"]), json={"name": "Mel", "weight_kg": 14.30}, headers=headers)

    assert response.status_code == 200
    assert response.json() == pet


# --- delete --------------------------------------------------------------------------------------


def test_delete_removes_events_and_keeps_expenses_without_the_pet(client, headers, ana, make, db_session):
    pet = make()
    other = make("Bidu")
    for target in (pet, other):
        response = client.post(
            f"{pet_url(target['id'])}/events",
            json={"type": "vet", "occurred_on": "2026-10-01"},
            headers=headers,
        )
        assert response.status_code == 201
    expense = Transaction(
        user_id=ana[0].id,
        type="expense",
        amount=Decimal("95.00"),
        category="Pets",
        due_date=date(2026, 10, 1),
        pet_id=uuid.UUID(pet["id"]),
    )
    db_session.add(expense)
    db_session.commit()

    response = client.delete(pet_url(pet["id"]), headers=headers)

    assert response.status_code == 204
    assert client.get(pet_url(pet["id"]), headers=headers).status_code == 404
    event_pets = db_session.scalars(select(PetEvent.pet_id)).all()
    assert [str(pet_id) for pet_id in event_pets] == [other["id"]]
    db_session.refresh(expense)
    assert (expense.pet_id, expense.user_id, expense.amount) == (None, ana[0].id, Decimal("95.00"))
    assert db_session.scalar(select(func.count()).select_from(Transaction)) == 1


# --- isolation and auth --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [
        ("GET", "", None),
        ("PATCH", "", {"name": "Invasão"}),
        ("DELETE", "", None),
        ("GET", "/events", None),
        ("POST", "/events", {"type": "vet", "occurred_on": "2026-10-01"}),
    ],
)
def test_other_users_pet_is_not_found(client, bia, make, method, suffix, body):
    pet = make()
    _, bia_headers = bia

    response = client.request(method, pet_url(pet["id"]) + suffix, json=body, headers=bia_headers)

    assert response.status_code == 404
    assert response.json() == {"detail": NOT_FOUND}


def test_list_only_shows_own_pets(client, bia, make):
    make()
    _, bia_headers = bia

    assert client.get(PETS_URL, headers=bia_headers).json()["total"] == 0


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", PETS_URL),
        ("GET", f"{PETS_URL}/reminders"),
        ("PATCH", pet_url(uuid.uuid4())),
        ("POST", f"{pet_url(uuid.uuid4())}/events"),
        ("PATCH", f"{pet_url(uuid.uuid4())}/events/{uuid.uuid4()}"),
    ],
)
def test_requires_authentication(client, method, path):
    response = client.request(method, path)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
