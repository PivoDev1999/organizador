from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.models import ShoppingItem
from app.schemas.common import MONEY_MAX, QUANTITY_MAX

SHOPPING_URL = "/api/shopping"
SUMMARY_URL = f"{SHOPPING_URL}/summary"
BASE = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def ana(authenticate):
    return authenticate("ana@example.test")


@pytest.fixture
def add(db_session, ana):
    """Insert straight into the database: lets each row have its own created_at/purchased_at."""
    user, _ = ana

    def _add(name: str, category: str = "Mercearia", user=user, **fields) -> ShoppingItem:
        if "purchased_at" in fields:
            fields["is_purchased"] = True
        item = ShoppingItem(user_id=user.id, name=name, category=category, **fields)
        db_session.add(item)
        db_session.commit()
        return item

    return _add


@pytest.fixture
def shopping_list(add, create_user) -> None:
    add("feijão", "Grãos", created_at=BASE + timedelta(days=3))
    add("Água", "Bebidas", created_at=BASE + timedelta(days=1), purchased_at=BASE + timedelta(days=5))
    add("Arroz", "Grãos", created_at=BASE + timedelta(days=2), purchased_at=BASE + timedelta(days=6))
    add("Detergente 100%", "Limpeza", created_at=BASE + timedelta(days=4))
    add("abacate", "Hortifruti", created_at=BASE)
    add("Arroz da Bia", "Grãos", user=create_user("bia@example.test"))


def names(client, headers, **params) -> list[str]:
    response = client.get(SHOPPING_URL, params=params, headers=headers)
    assert response.status_code == 200, response.text
    return [item["name"] for item in response.json()["items"]]


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({}, ["Água", "Arroz", "feijão", "abacate", "Detergente 100%"]),
        ({"is_purchased": "true"}, ["Água", "Arroz"]),
        ({"is_purchased": "false"}, ["feijão", "abacate", "Detergente 100%"]),
        ({"category": ["Grãos", "Bebidas", " "]}, ["Água", "Arroz", "feijão"]),
        ({"q": "ARR"}, ["Arroz"]),
        ({"q": "0%"}, ["Detergente 100%"]),
        ({"q": "_"}, []),
    ],
)
def test_filters_combine_and_only_show_own_items(client, ana, shopping_list, params, expected):
    assert names(client, ana[1], **params) == expected


@pytest.mark.parametrize(
    ("sort", "expected"),
    [
        ("name", ["abacate", "Água", "Arroz", "Detergente 100%", "feijão"]),
        ("-name", ["feijão", "Detergente 100%", "Arroz", "Água", "abacate"]),
        ("created_at", ["abacate", "Água", "Arroz", "feijão", "Detergente 100%"]),
        ("-created_at", ["Detergente 100%", "feijão", "Arroz", "Água", "abacate"]),
        ("-purchased_at", ["Arroz", "Água", "abacate", "Detergente 100%", "feijão"]),
    ],
)
def test_sort(client, ana, shopping_list, sort, expected):
    # "-purchased_at": pending items last, tied among themselves (broken by id), so compare as sets.
    result = names(client, ana[1], sort=sort)
    if sort == "-purchased_at":
        assert result[:2] == expected[:2] and set(result[2:]) == set(expected[2:])
    else:
        assert result == expected


def test_pagination_reports_total_of_all_matches(client, ana, shopping_list):
    response = client.get(SHOPPING_URL, params={"limit": 2, "offset": 1, "sort": "name"}, headers=ana[1])

    body = response.json()
    assert ([item["name"] for item in body["items"]], body["total"], body["limit"], body["offset"]) == (
        ["Água", "Arroz"],
        5,
        2,
        1,
    )


def test_list_rejects_unknown_sort(client, ana):
    response = client.get(SHOPPING_URL, params={"sort": "price"}, headers=ana[1])

    assert response.status_code == 422


# --- summary -----------------------------------------------------------------------------------


def summary(client, headers) -> dict:
    response = client.get(SUMMARY_URL, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_summary_of_an_empty_list(client, ana):
    assert summary(client, ana[1]) == {"pending": 0, "purchased": 0, "estimated_total": "0.00"}


def test_summary_counts_and_rounds_the_pending_total_half_even(client, ana, add, create_user):
    add("Arroz", quantity=Decimal(2), estimated_price=Decimal("10.00"))  # 20.00
    add("Pão", estimated_price=Decimal("5.50"))  # no quantity: 1 unit
    add("Frutas", quantity=Decimal(3))  # no price: adds nothing
    add("Sal", quantity=Decimal("0.5"), estimated_price=Decimal("0.05"))  # 0.025
    add("Papel", quantity=Decimal(1), estimated_price=Decimal(100), purchased_at=BASE)  # purchased
    add("Da Bia", estimated_price=Decimal(1000), user=create_user("bia@example.test"))

    # 25.525 -> 25.52 with ROUND_HALF_EVEN (25.53 with half-up).
    assert summary(client, ana[1]) == {"pending": 4, "purchased": 1, "estimated_total": "25.52"}


def test_summary_total_beyond_the_money_input_limit_is_reported_exactly(client, ana, add):
    for name in ("A", "B"):
        add(name, quantity=QUANTITY_MAX, estimated_price=MONEY_MAX)

    expected = 2 * QUANTITY_MAX * MONEY_MAX
    assert expected > MONEY_MAX
    assert summary(client, ana[1])["estimated_total"] == f"{expected.quantize(Decimal('0.01')):.2f}"
