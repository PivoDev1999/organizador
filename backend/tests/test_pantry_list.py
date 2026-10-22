from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.core import clock
from app.core.stock import expires_by, is_expired, is_low_stock

PANTRY_URL = "/api/pantry"
TODAY = date(2026, 10, 21)


def in_days(days: int) -> str:
    return (TODAY + timedelta(days=days)).isoformat()


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch) -> None:
    # 15:00 UTC is midday in America/Sao_Paulo: the same calendar day.
    monkeypatch.setattr(clock, "now_utc", lambda: datetime.combine(TODAY, time(15, 0), tzinfo=UTC))


@pytest.fixture
def headers(authenticate):
    return authenticate("ana@example.test")[1]


@pytest.fixture
def make(client, headers):
    def _make(name: str, **payload) -> dict:
        payload.setdefault("category", "Grãos")
        payload.setdefault("unit", "un")
        response = client.post(PANTRY_URL, json={"name": name, **payload}, headers=headers)
        assert response.status_code == 201, response.text
        return response.json()

    return _make


@pytest.fixture
def pantry(make) -> None:
    """A pantry covering every rule boundary."""
    make("Arroz", quantity="1", min_quantity="2", expires_on=in_days(180), location="Armário")
    make("Café", category="Bebidas", quantity="0.5", min_quantity="0.5", expires_on=in_days(-1))
    make(
        "Leite",
        category="Laticínios",
        quantity="6",
        min_quantity="2",
        expires_on=in_days(0),
        location="Geladeira",
    )
    make("Iogurte", category="Laticínios", quantity="4", expires_on=in_days(7), location="Geladeira")
    make("Detergente", category="Limpeza", quantity="3", min_quantity="2.999")
    make("Água", category="Bebidas", quantity="0", min_quantity="0", expires_on=in_days(8))
    make("feijão", quantity="2", expires_on=in_days(-30), location="Armário")


def names(client, headers, **params) -> list[str]:
    response = client.get(PANTRY_URL, params=params, headers=headers)
    assert response.status_code == 200, response.text
    return [item["name"] for item in response.json()["items"]]


def as_item(body: dict) -> SimpleNamespace:
    return SimpleNamespace(
        quantity=Decimal(body["quantity"]),
        min_quantity=Decimal(body["min_quantity"]) if body["min_quantity"] is not None else None,
        expires_on=date.fromisoformat(body["expires_on"]) if body["expires_on"] else None,
    )


# --- pure rules ------------------------------------------------------------------------------------


def stock(quantity, min_quantity=None, expires_on=None):
    return SimpleNamespace(
        quantity=Decimal(quantity),
        min_quantity=Decimal(min_quantity) if min_quantity is not None else None,
        expires_on=expires_on,
    )


@pytest.mark.parametrize(
    ("item", "low_stock", "expired"),
    [
        (stock("1", "2", TODAY - timedelta(days=1)), True, True),
        (stock("2", "2", TODAY), True, False),
        (stock("2.001", "2"), False, False),
        (stock("0"), False, False),
    ],
)
def test_pure_rules(item, low_stock, expired):
    assert (is_low_stock(item), is_expired(item, TODAY)) == (low_stock, expired)


@pytest.mark.parametrize(
    ("params", "rule"),
    [
        ({"low_stock": "true"}, is_low_stock),
        ({"expired": "true"}, lambda item: is_expired(item, TODAY)),
        ({"expiring_within": 7}, lambda item: expires_by(item, TODAY + timedelta(days=7))),
        ({"expiring_within": 0}, lambda item: expires_by(item, TODAY)),
    ],
)
def test_sql_filters_agree_with_pure_rules_and_flags(client, headers, pantry, params, rule):
    every = client.get(PANTRY_URL, headers=headers).json()["items"]
    for body in every:
        item = as_item(body)
        assert body["low_stock"] is is_low_stock(item)
        assert body["expired"] is is_expired(item, TODAY)

    assert set(names(client, headers, **params)) == {body["name"] for body in every if rule(as_item(body))}


# --- filters -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({}, ["Água", "Arroz", "Café", "Detergente", "feijão", "Iogurte", "Leite"]),
        ({"category": ["Bebidas", " Limpeza "]}, ["Água", "Café", "Detergente"]),
        ({"location": "Geladeira"}, ["Iogurte", "Leite"]),
        ({"q": "FEIJ"}, ["feijão"]),
        ({"q": "%"}, []),
        ({"low_stock": "true"}, ["Água", "Arroz", "Café"]),
        ({"low_stock": "false"}, ["Água", "Arroz", "Café", "Detergente", "feijão", "Iogurte", "Leite"]),
        ({"expiring_within": 7}, ["Café", "feijão", "Iogurte", "Leite"]),
        ({"expired": "true"}, ["Café", "feijão"]),
        ({"low_stock": "true", "expiring_within": 8}, ["Água", "Café"]),
    ],
)
def test_list_filters(client, headers, pantry, params, expected):
    assert names(client, headers, **params) == expected


@pytest.mark.parametrize(
    ("sort", "expected"),
    [
        ("name", ["Água", "Arroz", "Café", "Detergente", "feijão", "Iogurte", "Leite"]),
        ("-name", ["Leite", "Iogurte", "feijão", "Detergente", "Café", "Arroz", "Água"]),
        ("expires_on", ["feijão", "Café", "Leite", "Iogurte", "Água", "Arroz", "Detergente"]),
        ("-expires_on", ["Arroz", "Água", "Iogurte", "Leite", "Café", "feijão", "Detergente"]),
        ("quantity", ["Água", "Café", "Arroz", "feijão", "Detergente", "Iogurte", "Leite"]),
    ],
)
def test_list_sort(client, headers, pantry, sort, expected):
    # created_at is not covered here: every row of a test shares the transaction's now().
    assert names(client, headers, sort=sort) == expected


def test_list_paginates_with_total(client, headers, pantry):
    body = client.get(
        PANTRY_URL, params={"limit": 2, "offset": 2, "low_stock": "true"}, headers=headers
    ).json()

    assert [item["name"] for item in body["items"]] == ["Café"]
    assert (body["total"], body["limit"], body["offset"]) == (3, 2, 2)


@pytest.mark.parametrize(
    "params",
    [{"expiring_within": 366}, {"sort": "price"}],
)
def test_list_rejects_invalid_query(client, headers, params):
    assert client.get(PANTRY_URL, params=params, headers=headers).status_code == 422


# --- alerts ----------------------------------------------------------------------------------------


def test_alerts_split_and_order(client, headers, pantry):
    response = client.get(f"{PANTRY_URL}/alerts", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert {key: [item["name"] for item in items] for key, items in body.items()} == {
        "low_stock": ["Água", "Arroz", "Café"],
        "expired": ["feijão", "Café"],
        "expiring_soon": ["Leite", "Iogurte"],
    }
    assert body["expired"][1]["expired"] is True and body["expired"][1]["low_stock"] is True


@pytest.mark.parametrize(
    ("expiring_within", "expiring_soon"), [(0, ["Leite"]), (8, ["Leite", "Iogurte", "Água"])]
)
def test_alerts_window(client, headers, pantry, expiring_within, expiring_soon):
    body = client.get(
        f"{PANTRY_URL}/alerts", params={"expiring_within": expiring_within}, headers=headers
    ).json()

    assert [item["name"] for item in body["expiring_soon"]] == expiring_soon


def test_alerts_are_empty_for_a_new_user_and_reject_bad_window(client, headers):
    assert client.get(f"{PANTRY_URL}/alerts", headers=headers).json() == {
        "low_stock": [],
        "expired": [],
        "expiring_soon": [],
    }
    assert (
        client.get(f"{PANTRY_URL}/alerts", params={"expiring_within": 400}, headers=headers).status_code
        == 422
    )


# --- categories and locations ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("categories", ["Bebidas", "Grãos", "Laticínios", "Limpeza"]),
        ("locations", ["Armário", "Geladeira"]),
    ],
)
def test_distinct_values_are_sorted_and_isolated(client, headers, authenticate, pantry, path, expected):
    _, bia_headers = authenticate("bia@example.test")
    client.post(
        PANTRY_URL,
        json={"name": "X", "category": "Açougue", "unit": "kg", "location": "Freezer"},
        headers=bia_headers,
    )

    assert client.get(f"{PANTRY_URL}/{path}", headers=headers).json() == expected
    assert client.get(f"{PANTRY_URL}/{path}", headers=bia_headers).json() == [
        "Açougue" if path == "categories" else "Freezer"
    ]
