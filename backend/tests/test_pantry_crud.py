import uuid
from datetime import UTC, date, datetime, time

import pytest
from sqlalchemy import event, select

from app.core import clock
from app.models import ShoppingItem

PANTRY_URL = "/api/pantry"
NOT_FOUND = "Item não encontrado."
READ_FIELDS = {
    "id",
    "name",
    "category",
    "quantity",
    "unit",
    "min_quantity",
    "expires_on",
    "location",
    "low_stock",
    "expired",
    "created_at",
    "updated_at",
}


def item_url(item_id, suffix: str = "") -> str:
    return f"{PANTRY_URL}/{item_id}{suffix}"


@pytest.fixture
def ana(authenticate):
    return authenticate("ana@example.test")


@pytest.fixture
def bia(authenticate):
    return authenticate("bia@example.test")


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch) -> date:
    today = date(2026, 10, 21)
    # 15:00 UTC is midday in America/Sao_Paulo: the same calendar day.
    monkeypatch.setattr(clock, "now_utc", lambda: datetime.combine(today, time(15, 0), tzinfo=UTC))
    return today


@pytest.fixture
def make(client, ana):
    _, headers = ana

    def _make(**payload) -> dict:
        payload.setdefault("name", "Arroz")
        payload.setdefault("category", "Grãos")
        payload.setdefault("unit", "kg")
        response = client.post(PANTRY_URL, json=payload, headers=headers)
        assert response.status_code == 201, response.text
        return response.json()

    return _make


def messages(response) -> list[str]:
    detail = response.json()["detail"]
    return [detail] if isinstance(detail, str) else [error["msg"] for error in detail]


# --- create ------------------------------------------------------------------------------------


def test_create_with_defaults(client, ana):
    _, headers = ana

    response = client.post(
        PANTRY_URL,
        json={"name": "  Arroz  ", "category": " Grãos ", "unit": " kg ", "location": "   "},
        headers=headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == READ_FIELDS
    assert body | {"id": None, "created_at": None, "updated_at": None} == {
        "id": None,
        "name": "Arroz",
        "category": "Grãos",
        "quantity": "0.000",
        "unit": "kg",
        "min_quantity": None,
        "expires_on": None,
        "location": None,
        "low_stock": False,
        "expired": False,
        "created_at": None,
        "updated_at": None,
    }
    assert client.get(item_url(body["id"]), headers=headers).json() == body


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {"quantity": "1.5", "min_quantity": 2},
            {"quantity": "1.500", "min_quantity": "2.000", "low_stock": True},
        ),
        ({"quantity": 2, "min_quantity": "2"}, {"quantity": "2.000", "low_stock": True}),
        ({"expires_on": "2026-10-20"}, {"expired": True}),
        ({"expires_on": "2026-10-21"}, {"expired": False}),
    ],
)
def test_create_computes_flags_and_serializes_decimals_as_strings(make, payload, expected):
    body = make(**payload)

    assert {key: body[key] for key in expected} == expected


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"quantity": "1.0005"}, "Use no máximo 3 casas decimais."),
        ({"quantity": "10000000"}, "O valor deve ser no máximo 9999999.999."),
        ({"quantity": "-1"}, "O valor deve ser maior ou igual a 0."),
        ({"quantity": "NaN"}, "Informe um número válido (ex.: 1.5)."),
        ({"quantity": True}, "Informe um número válido (ex.: 1.5)."),
        ({"quantity": None}, "Este campo não pode ser nulo."),
        ({"name": "   "}, "Informe o nome."),
        ({"category": ""}, "Informe a categoria."),
        ({"unit": "x" * 21}, "A unidade deve ter no máximo 20 caracteres."),
        ({"user_id": str(uuid.uuid4())}, "Campo não permitido."),
    ],
)
def test_create_rejects_invalid_fields(client, ana, payload, message):
    _, headers = ana
    body = {"name": "Arroz", "category": "Grãos", "unit": "kg", **payload}

    response = client.post(PANTRY_URL, json=body, headers=headers)

    assert response.status_code == 422
    assert messages(response) == [message]


@pytest.mark.parametrize("field", ["category", "unit"])
def test_create_requires_category_and_unit(client, ana, field):
    _, headers = ana
    body = {"name": "Arroz", "category": "Grãos", "unit": "kg"}
    del body[field]

    response = client.post(PANTRY_URL, json=body, headers=headers)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", field]


def test_validation_message_does_not_echo_input(client, ana):
    _, headers = ana
    secret = "123.45678"

    response = client.post(
        PANTRY_URL, json={"name": "X", "category": "Y", "unit": "kg", "quantity": secret}, headers=headers
    )

    assert response.status_code == 422
    assert secret not in response.text


# --- update ------------------------------------------------------------------------------------


def test_patch_changes_only_sent_fields_and_clears_nullable_ones(client, ana, make):
    _, headers = ana
    item = make(quantity="3", min_quantity="1", expires_on="2026-11-01", location="Armário")

    response = client.patch(
        item_url(item["id"]),
        json={"quantity": "0.5", "min_quantity": None, "expires_on": None, "location": "  Geladeira "},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["quantity"] == "0.500"
    assert body["min_quantity"] is None
    assert body["expires_on"] is None
    assert body["location"] == "Geladeira"
    assert (body["name"], body["category"], body["unit"]) == ("Arroz", "Grãos", "kg")
    assert body["low_stock"] is False


@pytest.mark.parametrize("field", ["name", "category", "unit", "quantity"])
def test_patch_rejects_null_for_required_fields(client, ana, make, field):
    _, headers = ana
    item = make()

    response = client.patch(item_url(item["id"]), json={field: None}, headers=headers)

    assert response.status_code == 422
    assert messages(response) == ["Este campo não pode ser nulo."]


def test_noop_patch_issues_no_update(client, ana, make, db_session):
    _, headers = ana
    item = make(quantity="1.5")
    statements: list[str] = []
    connection = db_session.connection()
    listener = lambda *args: statements.append(args[2])  # noqa: E731 - (conn, cursor, statement, ...)
    event.listen(connection, "before_cursor_execute", listener)
    try:
        # "1.50" equals the stored 1.500: not a change.
        response = client.patch(
            item_url(item["id"]), json={"name": "Arroz", "quantity": "1.50"}, headers=headers
        )
    finally:
        event.remove(connection, "before_cursor_execute", listener)

    assert response.status_code == 200
    assert response.json() == item
    assert not [sql for sql in statements if sql.lstrip().upper().startswith("UPDATE PANTRY_ITEMS")]


# --- delete ------------------------------------------------------------------------------------


def test_delete_keeps_linked_shopping_item_without_link(client, ana, make, db_session):
    user, headers = ana
    item = make()
    shopping = ShoppingItem(
        user_id=user.id, name="Arroz", category="Grãos", pantry_item_id=uuid.UUID(item["id"])
    )
    db_session.add(shopping)
    db_session.commit()

    response = client.delete(item_url(item["id"]), headers=headers)

    assert response.status_code == 204
    assert client.get(item_url(item["id"]), headers=headers).status_code == 404
    db_session.expire_all()
    remaining = db_session.scalar(select(ShoppingItem).where(ShoppingItem.id == shopping.id))
    assert remaining is not None
    assert remaining.pantry_item_id is None


# --- isolation and auth ------------------------------------------------------------------------

ITEM_ROUTES = [
    ("GET", "", None),
    ("PATCH", "", {"name": "Outro"}),
    ("DELETE", "", None),
    ("POST", "/consume", {"amount": "1"}),
    ("POST", "/restock", {"amount": "1"}),
]


@pytest.mark.parametrize(("method", "suffix", "body"), ITEM_ROUTES)
def test_other_users_item_is_not_found_and_untouched(client, ana, bia, make, method, suffix, body):
    item = make(quantity="5")
    _, bia_headers = bia

    response = client.request(method, item_url(item["id"], suffix), json=body, headers=bia_headers)

    assert response.status_code == 404
    assert response.json() == {"detail": NOT_FOUND}
    assert client.get(item_url(item["id"]), headers=ana[1]).json() == item


@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("GET", PANTRY_URL),
        ("POST", PANTRY_URL),
        ("GET", f"{PANTRY_URL}/alerts"),
        ("POST", item_url(uuid.uuid4(), "/consume")),
    ],
)
def test_endpoints_require_authentication(client, method, url):
    response = client.request(method, url, json={})

    assert response.status_code == 401
