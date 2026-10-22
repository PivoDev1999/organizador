import pytest

PANTRY_URL = "/api/pantry"


@pytest.fixture
def headers(authenticate):
    return authenticate("ana@example.test")[1]


@pytest.fixture
def item(client, headers) -> dict:
    payload = {"name": "Leite", "category": "Laticínios", "unit": "L", "quantity": "5", "min_quantity": "2"}
    response = client.post(PANTRY_URL, json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def change(client, headers, item: dict, action: str, amount):
    return client.post(f"{PANTRY_URL}/{item['id']}/{action}", json={"amount": amount}, headers=headers)


def stored_quantity(client, headers, item: dict) -> str:
    return client.get(f"{PANTRY_URL}/{item['id']}", headers=headers).json()["quantity"]


@pytest.mark.parametrize(
    ("amount", "quantity", "low_stock"),
    [("1.5", "3.500", False), (3, "2.000", True), ("5", "0.000", True)],
)
def test_consume(client, headers, item, amount, quantity, low_stock):
    response = change(client, headers, item, "consume", amount)

    assert response.status_code == 200
    assert (response.json()["quantity"], response.json()["low_stock"]) == (quantity, low_stock)
    assert stored_quantity(client, headers, item) == quantity


def test_consume_more_than_stored_is_a_conflict_and_keeps_quantity(client, headers, item):
    response = change(client, headers, item, "consume", "5.001")

    assert response.status_code == 409
    assert response.json() == {"detail": "Quantidade insuficiente."}
    assert stored_quantity(client, headers, item) == "5.000"


@pytest.mark.parametrize(("amount", "quantity"), [("0.5", "5.500"), (9999994.999, "9999999.999")])
def test_restock(client, headers, item, amount, quantity):
    response = change(client, headers, item, "restock", amount)

    assert response.status_code == 200
    assert response.json()["quantity"] == quantity
    assert stored_quantity(client, headers, item) == quantity


def test_restock_beyond_the_column_limit_is_422_and_keeps_quantity(client, headers, item):
    response = change(client, headers, item, "restock", "9999995")

    assert response.status_code == 422
    assert response.json()["detail"] == [
        {
            "type": "value_error",
            "loc": ["body"],
            "msg": "A quantidade em estoque não pode passar de 9999999.999.",
        }
    ]
    assert stored_quantity(client, headers, item) == "5.000"


@pytest.mark.parametrize(
    ("action", "body", "message"),
    [
        ("consume", {"amount": "0"}, "O valor deve ser maior que 0."),
        ("restock", {"amount": -1}, "O valor deve ser maior que 0."),
        ("consume", {"amount": "1.0001"}, "Use no máximo 3 casas decimais."),
        ("restock", {"amount": False}, "Informe um número válido (ex.: 1.5)."),
        ("consume", {"amount": "1", "unit": "kg"}, "Campo não permitido."),
    ],
)
def test_stock_change_validates_amount(client, headers, item, action, body, message):
    response = client.post(f"{PANTRY_URL}/{item['id']}/{action}", json=body, headers=headers)

    assert response.status_code == 422
    assert [error["msg"] for error in response.json()["detail"]] == [message]
    assert stored_quantity(client, headers, item) == "5.000"
