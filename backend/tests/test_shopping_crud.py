import uuid

import pytest
from sqlalchemy import event, func, select

from app.models import ShoppingItem

SHOPPING_URL = "/api/shopping"
PANTRY_URL = "/api/pantry"
NOT_FOUND = "Item da lista não encontrado."
PANTRY_NOT_FOUND = "Item da despensa não encontrado."
READ_FIELDS = {
    "id",
    "name",
    "category",
    "quantity",
    "unit",
    "estimated_price",
    "is_purchased",
    "purchased_at",
    "pantry_item_id",
    "created_at",
    "updated_at",
}


def item_url(item_id, suffix: str = "") -> str:
    return f"{SHOPPING_URL}/{item_id}{suffix}"


@pytest.fixture
def ana(authenticate):
    return authenticate("ana@example.test")


@pytest.fixture
def bia(authenticate):
    return authenticate("bia@example.test")


@pytest.fixture
def make(client, ana):
    _, headers = ana

    def _make(**payload) -> dict:
        payload.setdefault("name", "Arroz")
        payload.setdefault("category", "Grãos")
        response = client.post(SHOPPING_URL, json=payload, headers=headers)
        assert response.status_code == 201, response.text
        return response.json()

    return _make


def make_pantry_item(client, headers) -> str:
    payload = {"name": "Arroz", "category": "Grãos", "unit": "kg"}
    response = client.post(PANTRY_URL, json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def messages(response) -> list[str]:
    detail = response.json()["detail"]
    return [detail] if isinstance(detail, str) else [error["msg"] for error in detail]


def count_items(db_session) -> int:
    return db_session.scalar(select(func.count()).select_from(ShoppingItem))


# --- create ------------------------------------------------------------------------------------


def test_create_with_defaults_trims_text_and_reads_back(client, ana):
    _, headers = ana

    response = client.post(
        SHOPPING_URL, json={"name": "  Arroz ", "category": " Grãos ", "unit": "   "}, headers=headers
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == READ_FIELDS
    assert {key: body[key] for key in READ_FIELDS - {"id", "created_at", "updated_at"}} == {
        "name": "Arroz",
        "category": "Grãos",
        "quantity": None,
        "unit": None,
        "estimated_price": None,
        "is_purchased": False,
        "purchased_at": None,
        "pantry_item_id": None,
    }
    assert client.get(item_url(body["id"]), headers=headers).json() == body


@pytest.mark.parametrize(("price", "stored"), [("12.9", "12.90"), (12, "12.00"), ("0", "0.00")])
def test_create_with_every_field_serializes_decimals_as_strings(client, ana, price, stored):
    _, headers = ana
    pantry_item_id = make_pantry_item(client, headers)
    payload = {
        "name": "Arroz",
        "category": "Grãos",
        "quantity": 1.5,
        "unit": "kg",
        "estimated_price": price,
        "pantry_item_id": pantry_item_id,
    }

    response = client.post(SHOPPING_URL, json=payload, headers=headers)

    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["quantity"], body["estimated_price"], body["pantry_item_id"]) == (
        "1.500",
        stored,
        pantry_item_id,
    )


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"name": "   "}, "Informe o nome."),
        ({"category": ""}, "Informe a categoria."),
        ({"quantity": "0"}, "O valor deve ser maior que 0."),
        ({"estimated_price": "-0.01"}, "O valor deve ser maior ou igual a 0."),
        ({"estimated_price": 12.9}, 'Envie valores em dinheiro como texto (ex.: "12.90").'),
        ({"estimated_price": "1.999"}, "Use no máximo 2 casas decimais."),
        ({"unit": "u" * 21}, "A unidade deve ter no máximo 20 caracteres."),
        ({"is_purchased": True}, "Campo não permitido."),
        ({"pantry_item_id": "abc"}, "Identificador inválido."),
    ],
)
def test_create_rejects_invalid_fields(client, ana, db_session, payload, message):
    _, headers = ana

    response = client.post(
        SHOPPING_URL, json={"name": "Arroz", "category": "Grãos", **payload}, headers=headers
    )

    assert response.status_code == 422
    assert messages(response) == [message]
    assert count_items(db_session) == 0


def test_create_requires_name_and_category(client, ana):
    response = client.post(SHOPPING_URL, json={}, headers=ana[1])

    assert response.status_code == 422
    assert {tuple(error["loc"]) for error in response.json()["detail"]} == {
        ("body", "name"),
        ("body", "category"),
    }


def test_validation_message_does_not_echo_input(client, ana):
    secret = "segredo-" + "x" * 300

    response = client.post(SHOPPING_URL, json={"name": secret, "category": secret}, headers=ana[1])

    assert response.status_code == 422
    assert "segredo" not in response.text


@pytest.mark.parametrize("owner", ["bia", "nobody"])
def test_create_with_someone_elses_pantry_item_is_422(client, ana, bia, db_session, owner):
    pantry_item_id = make_pantry_item(client, bia[1]) if owner == "bia" else str(uuid.uuid4())

    response = client.post(
        SHOPPING_URL,
        json={"name": "Arroz", "category": "Grãos", "pantry_item_id": pantry_item_id},
        headers=ana[1],
    )

    assert response.status_code == 422
    assert response.json()["detail"] == [{"type": "value_error", "loc": ["body"], "msg": PANTRY_NOT_FOUND}]
    assert count_items(db_session) == 0


# --- update ------------------------------------------------------------------------------------


def test_patch_changes_only_sent_fields_and_clears_nullable_ones(client, ana, make):
    _, headers = ana
    item = make(quantity="2", unit="kg", estimated_price="10")

    response = client.patch(
        item_url(item["id"]), json={"name": "Arroz integral", "unit": None, "quantity": None}, headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["name"], body["category"], body["unit"], body["quantity"], body["estimated_price"]) == (
        "Arroz integral",
        "Grãos",
        None,
        None,
        "10.00",
    )


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"name": None}, "Este campo não pode ser nulo."),
        ({"category": None}, "Este campo não pode ser nulo."),
        ({"is_purchased": True}, "Campo não permitido."),
        ({"purchased_at": "2026-10-21T10:00:00Z"}, "Campo não permitido."),
    ],
)
def test_patch_rejects_null_required_fields_and_purchase_state(client, ana, make, payload, message):
    _, headers = ana
    item = make()

    response = client.patch(item_url(item["id"]), json=payload, headers=headers)

    assert response.status_code == 422
    assert messages(response) == [message]
    assert client.get(item_url(item["id"]), headers=headers).json() == item


def test_noop_patch_issues_no_update(client, ana, make, db_session):
    _, headers = ana
    item = make(quantity="1.5", estimated_price="3")
    statements: list[str] = []
    connection = db_session.connection()
    listener = lambda *args: statements.append(args[2])  # noqa: E731 - (conn, cursor, statement, ...)
    event.listen(connection, "before_cursor_execute", listener)
    try:
        # "1.50" equals the stored 1.500 and "3.00" the stored 3.00: not a change.
        response = client.patch(
            item_url(item["id"]),
            json={"name": "Arroz", "quantity": "1.50", "estimated_price": "3.00"},
            headers=headers,
        )
    finally:
        event.remove(connection, "before_cursor_execute", listener)

    assert response.status_code == 200
    assert response.json() == item
    assert not [sql for sql in statements if sql.lstrip().upper().startswith("UPDATE SHOPPING_ITEMS")]


def test_patch_links_and_unlinks_own_pantry_item(client, ana, make):
    _, headers = ana
    item = make()
    pantry_item_id = make_pantry_item(client, headers)

    linked = client.patch(item_url(item["id"]), json={"pantry_item_id": pantry_item_id}, headers=headers)
    unlinked = client.patch(item_url(item["id"]), json={"pantry_item_id": None}, headers=headers)

    assert linked.json()["pantry_item_id"] == pantry_item_id
    assert unlinked.json()["pantry_item_id"] is None


def test_patch_with_someone_elses_pantry_item_is_422_and_keeps_item(client, ana, bia, make):
    _, headers = ana
    item = make()

    response = client.patch(
        item_url(item["id"]), json={"pantry_item_id": make_pantry_item(client, bia[1])}, headers=headers
    )

    assert response.status_code == 422
    assert messages(response) == [PANTRY_NOT_FOUND]
    assert client.get(item_url(item["id"]), headers=headers).json() == item


# --- delete ------------------------------------------------------------------------------------


def test_delete(client, ana, make):
    _, headers = ana
    item = make()

    response = client.delete(item_url(item["id"]), headers=headers)

    assert response.status_code == 204
    assert client.get(item_url(item["id"]), headers=headers).status_code == 404


# --- isolation and auth ------------------------------------------------------------------------

ITEM_ROUTES = [
    ("GET", "", None),
    ("PATCH", "", {"name": "Outro"}),
    ("DELETE", "", None),
    ("POST", "/purchase", None),
    ("POST", "/unpurchase", None),
]


@pytest.mark.parametrize(("method", "suffix", "body"), ITEM_ROUTES)
def test_other_users_item_is_not_found_and_untouched(client, ana, bia, make, method, suffix, body):
    item = make()

    response = client.request(method, item_url(item["id"], suffix), json=body, headers=bia[1])

    assert response.status_code == 404
    assert response.json() == {"detail": NOT_FOUND}
    assert client.get(item_url(item["id"]), headers=ana[1]).json() == item


@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("GET", SHOPPING_URL),
        ("POST", SHOPPING_URL),
        ("GET", f"{SHOPPING_URL}/summary"),
        ("POST", f"{SHOPPING_URL}/from-pantry"),
        ("DELETE", f"{SHOPPING_URL}/purchased"),
        ("POST", item_url(uuid.uuid4(), "/purchase")),
    ],
)
def test_endpoints_require_authentication(client, method, url):
    response = client.request(method, url, json={})

    assert response.status_code == 401
