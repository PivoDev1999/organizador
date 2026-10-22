from datetime import UTC, date, datetime, time, timedelta

import pytest

from app.core import clock

SHOPPING_URL = "/api/shopping"
PANTRY_URL = "/api/pantry"
FROM_PANTRY_URL = f"{SHOPPING_URL}/from-pantry"
TODAY = date(2026, 10, 21)
NOW = datetime.combine(TODAY, time(15, 0), tzinfo=UTC)  # midday in America/Sao_Paulo


@pytest.fixture(autouse=True)
def frozen_now(monkeypatch) -> None:
    monkeypatch.setattr(clock, "now_utc", lambda: NOW)


@pytest.fixture
def ana(authenticate):
    return authenticate("ana@example.test")


@pytest.fixture
def bia(authenticate):
    return authenticate("bia@example.test")


def post(client, url: str, headers: dict, payload: dict | None = None, **params):
    return client.post(url, json=payload, params=params, headers=headers)


def make_pantry(client, headers, name: str = "Arroz", **payload) -> dict:
    payload = {"name": name, "category": "Grãos", "unit": "kg", "quantity": "1", **payload}
    response = post(client, PANTRY_URL, headers, payload)
    assert response.status_code == 201, response.text
    return response.json()


def make_item(client, headers, **payload) -> dict:
    payload = {"name": "Arroz", "category": "Grãos", **payload}
    response = post(client, SHOPPING_URL, headers, payload)
    assert response.status_code == 201, response.text
    return response.json()


def pantry_quantity(client, headers, pantry_item: dict) -> str:
    return client.get(f"{PANTRY_URL}/{pantry_item['id']}", headers=headers).json()["quantity"]


def get_item(client, headers, item: dict) -> dict:
    return client.get(f"{SHOPPING_URL}/{item['id']}", headers=headers).json()


def purchase(client, headers, item: dict, action: str = "purchase"):
    return post(client, f"{SHOPPING_URL}/{item['id']}/{action}", headers)


# --- purchase / unpurchase ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("item_fields", "linked", "restocked", "pantry_after"),
    [
        ({"quantity": "2.5", "unit": "  KG "}, True, True, "3.500"),  # same unit, other case/spaces
        ({"quantity": "2", "unit": "g"}, True, False, "1.000"),  # different unit
        ({"unit": "kg"}, True, False, "1.000"),  # no quantity
        ({"quantity": "2", "unit": "kg"}, False, False, "1.000"),  # not linked
    ],
)
def test_purchase_restocks_the_linked_pantry_item_only_when_it_can(
    client, ana, item_fields, linked, restocked, pantry_after
):
    _, headers = ana
    pantry_item = make_pantry(client, headers)
    if linked:
        item_fields = {**item_fields, "pantry_item_id": pantry_item["id"]}
    item = make_item(client, headers, **item_fields)

    response = purchase(client, headers, item)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["is_purchased"], body["pantry_restocked"]) == (True, restocked)
    assert datetime.fromisoformat(body["purchased_at"]) == NOW
    stored = get_item(client, headers, item)
    assert {key: body[key] for key in stored} == stored  # the purchase was committed
    assert pantry_quantity(client, headers, pantry_item) == pantry_after


def test_purchase_beyond_the_pantry_limit_is_422_and_saves_nothing(client, ana):
    _, headers = ana
    pantry_item = make_pantry(client, headers, quantity="9999999")
    item = make_item(client, headers, quantity="1", unit="kg", pantry_item_id=pantry_item["id"])

    response = purchase(client, headers, item)

    assert response.status_code == 422
    assert response.json()["detail"] == [
        {
            "type": "value_error",
            "loc": ["body"],
            "msg": "A compra deixaria o estoque da despensa acima de 9999999.999. "
            "Ajuste a quantidade do item ou da despensa; nada foi registrado.",
        }
    ]
    assert get_item(client, headers, item) == item
    assert pantry_quantity(client, headers, pantry_item) == "9999999.000"


def test_purchase_twice_is_a_conflict_and_restocks_once(client, ana):
    _, headers = ana
    pantry_item = make_pantry(client, headers)
    item = make_item(client, headers, quantity="1", unit="kg", pantry_item_id=pantry_item["id"])
    purchase(client, headers, item)

    response = purchase(client, headers, item)

    assert response.status_code == 409
    assert response.json() == {"detail": "Item já comprado."}
    assert pantry_quantity(client, headers, pantry_item) == "2.000"


def test_unpurchase_puts_item_back_without_touching_the_pantry(client, ana):
    _, headers = ana
    pantry_item = make_pantry(client, headers)
    item = make_item(client, headers, quantity="1", unit="kg", pantry_item_id=pantry_item["id"])
    purchase(client, headers, item)

    response = purchase(client, headers, item, "unpurchase")

    assert response.status_code == 200
    assert (response.json()["is_purchased"], response.json()["purchased_at"]) == (False, None)
    assert "pantry_restocked" not in response.json()
    assert pantry_quantity(client, headers, pantry_item) == "2.000"


def test_unpurchase_of_a_pending_item_is_a_conflict(client, ana):
    _, headers = ana
    item = make_item(client, headers)

    response = purchase(client, headers, item, "unpurchase")

    assert response.status_code == 409
    assert response.json() == {"detail": "Item não está comprado."}
    assert get_item(client, headers, item) == item


def test_unpurchase_is_a_conflict_when_another_pending_item_is_linked(client, ana):
    _, headers = ana
    pantry_item = make_pantry(client, headers, quantity="0", min_quantity="5")
    item = make_item(client, headers, quantity="1", unit="kg", pantry_item_id=pantry_item["id"])
    purchase(client, headers, item)
    post(client, FROM_PANTRY_URL, headers)  # still low: a new pending item for the same pantry item

    response = purchase(client, headers, item, "unpurchase")

    assert response.status_code == 409
    assert response.json() == {"detail": "Já existe um item pendente na lista para este item da despensa."}
    assert get_item(client, headers, item)["is_purchased"] is True


# --- from-pantry -------------------------------------------------------------------------------


@pytest.fixture
def pantry(client, ana) -> dict[str, dict]:
    """A pantry covering every rule boundary."""
    _, headers = ana
    yesterday = (TODAY - timedelta(days=1)).isoformat()
    return {
        "rice": make_pantry(client, headers, "Arroz", quantity="1", min_quantity="2.5"),  # low
        "coffee": make_pantry(
            client, headers, "Café", category="Bebidas", quantity="0.5", min_quantity="0.5"
        ),  # at the minimum: low, but nothing missing
        "beans": make_pantry(
            client, headers, "Feijão", quantity="0", min_quantity="1", expires_on=yesterday
        ),  # low and expired
        "milk": make_pantry(
            client,
            headers,
            "Leite",
            category="Laticínios",
            unit="L",
            quantity="6",
            min_quantity="2",
            expires_on=yesterday,
        ),  # expired only
        "yogurt": make_pantry(client, headers, "Iogurte", quantity="4", expires_on=TODAY.isoformat()),
    }


def summarize(items: list[dict]) -> list[tuple]:
    return [(i["name"], i["category"], i["unit"], i["quantity"], i["pantry_item_id"]) for i in items]


@pytest.mark.parametrize("include_expired", [False, True])
def test_from_pantry_creates_items_for_low_stock(client, ana, pantry, include_expired):
    _, headers = ana

    response = post(client, FROM_PANTRY_URL, headers, include_expired=include_expired)

    assert response.status_code == 201
    expected = [
        ("Arroz", "Grãos", "kg", "1.500", pantry["rice"]["id"]),
        ("Café", "Bebidas", "kg", None, pantry["coffee"]["id"]),
        ("Feijão", "Grãos", "kg", "1.000", pantry["beans"]["id"]),
    ]
    if include_expired:
        expected.append(("Leite", "Laticínios", "L", None, pantry["milk"]["id"]))
    assert summarize(response.json()) == expected
    assert all(not item["is_purchased"] and item["estimated_price"] is None for item in response.json())
    listed = client.get(SHOPPING_URL, params={"sort": "name"}, headers=headers).json()["items"]
    assert summarize(listed) == expected


def test_from_pantry_is_idempotent_while_items_are_pending(client, ana, pantry):
    _, headers = ana
    first = post(client, FROM_PANTRY_URL, headers).json()

    again = post(client, FROM_PANTRY_URL, headers)
    rice = next(item for item in first if item["pantry_item_id"] == pantry["rice"]["id"])
    # Buying 1.5 kg brings rice to 2.5 kg: still at the minimum, so it gets a new pending item.
    purchase(client, headers, rice)
    after_purchase = post(client, FROM_PANTRY_URL, headers)

    assert (again.status_code, again.json()) == (200, [])
    assert after_purchase.status_code == 201
    assert summarize(after_purchase.json()) == [("Arroz", "Grãos", "kg", None, pantry["rice"]["id"])]


def test_from_pantry_skips_only_items_with_a_pending_link(client, ana, pantry):
    _, headers = ana
    # A purchased item linked to rice does not count; a pending one linked to coffee does.
    rice_item = make_item(client, headers, pantry_item_id=pantry["rice"]["id"])
    post(client, f"{SHOPPING_URL}/{rice_item['id']}/purchase", headers)
    make_item(client, headers, name="Café", pantry_item_id=pantry["coffee"]["id"])

    response = post(client, FROM_PANTRY_URL, headers)

    assert [item["name"] for item in response.json()] == ["Arroz", "Feijão"]


def test_from_pantry_only_reads_and_writes_own_items(client, ana, bia, pantry):
    _, bia_headers = bia
    make_pantry(client, bia_headers, "Sal da Bia", quantity="0", min_quantity="1")

    bia_response = post(client, FROM_PANTRY_URL, bia_headers)
    ana_response = post(client, FROM_PANTRY_URL, ana[1])

    assert [item["name"] for item in bia_response.json()] == ["Sal da Bia"]
    assert [item["name"] for item in ana_response.json()] == ["Arroz", "Café", "Feijão"]


# --- delete purchased --------------------------------------------------------------------------


def test_delete_purchased_removes_only_own_purchased_items(client, ana, bia):
    _, headers = ana
    bought = make_item(client, headers, name="Comprado")
    pending = make_item(client, headers, name="Pendente")
    bias_bought = make_item(client, bia[1], name="Da Bia")
    for owner_headers, item in ((headers, bought), (bia[1], bias_bought)):
        purchase(client, owner_headers, item)

    response = client.delete(f"{SHOPPING_URL}/purchased", headers=headers)

    assert response.status_code == 204
    assert [i["name"] for i in client.get(SHOPPING_URL, headers=headers).json()["items"]] == ["Pendente"]
    assert get_item(client, headers, pending)["name"] == "Pendente"
    assert get_item(client, bia[1], bias_bought)["is_purchased"] is True
