from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.core import clock
from app.core.finance import budget_spent, month_bounds, paid_at_for, paid_on_of, percent_used, summarize
from app.models import Budget, Transaction

URL = "/api/transactions"
SUMMARY_URL = f"{URL}/summary"
NOW = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)  # 12:00 of 2026-10-21 in America/Sao_Paulo
SAO_PAULO = ZoneInfo("America/Sao_Paulo")
ZEROS = {"total": "0.00", "paid": "0.00", "pending": "0.00"}


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
def insert(db_session, ana):
    """Insert straight into the database: lets a test choose `created_at` (one transaction shares now())."""

    def _insert(category: str, amount: str, due: str, type_: str = "expense", paid: bool = False, **fields):
        transaction = Transaction(
            user_id=fields.pop("user_id", ana[0].id),
            type=type_,
            amount=Decimal(amount),
            category=category,
            due_date=date.fromisoformat(due),
            paid_at=NOW if paid else None,
            **fields,
        )
        db_session.add(transaction)
        db_session.commit()
        return transaction

    return _insert


def summary(client, headers, **params) -> dict:
    response = client.get(SUMMARY_URL, params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


# --- summary -------------------------------------------------------------------------------------


def test_summary_uses_the_due_month_paid_or_not(client, headers, insert):
    insert("Salário", "6500.00", "2026-10-01", "income", paid=True)
    insert("Freela", "500.00", "2026-10-31", "income")
    insert("Moradia", "1800.00", "2026-10-10", paid=True)
    insert("Moradia", "245.90", "2026-10-31")  # pending: still counts in October
    insert("Moradia", "999.99", "2026-11-01", paid=True)  # paid in October? the due month decides
    insert("Moradia", "1.00", "2026-09-30")

    body = summary(client, headers)  # default: the current month in the app timezone

    assert body["month"] == "2026-10"
    assert body["income"] == {"total": "7000.00", "paid": "6500.00", "pending": "500.00"}
    assert body["expense"] == {"total": "2045.90", "paid": "1800.00", "pending": "245.90"}
    assert body["balance"] == {"total": "4954.10", "paid": "4700.00"}


def test_summary_balance_can_be_negative_and_empty_month_is_zero(client, headers, insert):
    insert("Aluguel", "1800.00", "2026-12-05", paid=True)
    insert("Bônus", "100.00", "2026-12-20", "income")

    december = summary(client, headers, month="2026-12")

    assert december["balance"] == {"total": "-1700.00", "paid": "-1800.00"}
    assert summary(client, headers, month="2027-01") == {
        "month": "2027-01",
        "income": ZEROS,
        "expense": ZEROS,
        "balance": {"total": "0.00", "paid": "0.00"},
        "by_category": [],
    }


def test_by_category_groups_without_case_and_shows_the_newest_spelling(client, headers, insert):
    base = datetime(2026, 10, 1, tzinfo=UTC)
    insert("mercado", "100.00", "2026-10-02", paid=True, created_at=base)
    insert("MERCADO", "50.00", "2026-10-03", created_at=base + timedelta(hours=2))
    insert("Mercado", "25.50", "2026-10-04", created_at=base + timedelta(hours=1))
    insert("Íntimo", "10.00", "2026-10-05", created_at=base)
    insert("íntimo", "10.00", "2026-10-06", created_at=base + timedelta(hours=1))
    insert("Mercado", "40.00", "2026-10-07", "income", created_at=base)  # another type: another group

    by_category = summary(client, headers)["by_category"]

    assert by_category == [
        {"type": "expense", "category": "MERCADO", "total": "175.50", "paid": "100.00", "pending": "75.50"},
        {"type": "expense", "category": "íntimo", "total": "20.00", "paid": "0.00", "pending": "20.00"},
        {"type": "income", "category": "Mercado", "total": "40.00", "paid": "0.00", "pending": "40.00"},
    ]


# --- categories ----------------------------------------------------------------------------------


def test_categories_are_distinct_without_case_sorted_and_isolated(client, headers, authenticate, insert):
    base = datetime(2026, 10, 1, tzinfo=UTC)
    insert("mercado", "1", "2026-10-01", created_at=base)
    insert("Mercado", "1", "2026-10-01", created_at=base + timedelta(hours=1))
    insert("Água", "1", "2026-10-01")
    insert("banho", "1", "2026-10-01")
    bia, bia_headers = authenticate("bia@example.test")
    insert("Lazer", "1", "2026-10-01", user_id=bia.id)

    # pt-BR order: byte order would put "Água" last.
    assert client.get(f"{URL}/categories", headers=headers).json() == ["Água", "banho", "Mercado"]
    assert client.get(f"{URL}/categories", headers=bia_headers).json() == ["Lazer"]


# --- SQL and pure rules agree --------------------------------------------------------------------


def test_sql_agrees_with_the_pure_rules(client, headers, insert, db_session, ana):
    base = datetime(2026, 10, 1, tzinfo=UTC)
    # Month edges, both types, both states, and categories that tell lower-case rules apart: ICU's lower
    # matches str.lower() ("İ", final sigma), not casefold() ("Straße" vs "STRASSE").
    rows = [
        ("Straße", "10.00", "2026-10-01", "expense", True),
        ("STRASSE", "20.00", "2026-10-31", "expense", False),
        ("İMUNO", "30.00", "2026-10-15", "expense", False),
        ("i̇muno", "40.00", "2026-10-16", "expense", True),
        ("ΟΔΟΣ", "5.55", "2026-10-02", "expense", False),
        ("οδος", "4.45", "2026-10-03", "expense", True),
        ("οδος", "1.00", "2026-10-03", "income", True),
        ("Salário", "6500.00", "2026-10-05", "income", True),
        ("Salário", "9.99", "2026-09-30", "income", True),
        ("Straße", "7.00", "2026-11-01", "expense", False),
    ]
    for index, (category, amount, due, type_, paid) in enumerate(rows):
        insert(category, amount, due, type_, paid, created_at=base + timedelta(minutes=index))
    for category in ("straße", "STRASSE", "i̇muno", "οδος", "Lazer"):
        db_session.add(Budget(user_id=ana[0].id, category=category, month=date(2026, 10, 1), amount=100))
    db_session.commit()
    stored = list(db_session.scalars(select(Transaction)))

    for month in ("2026-09", "2026-10", "2026-11"):
        expected = summarize(stored, date.fromisoformat(f"{month}-01"))
        body = summary(client, headers, month=month)
        assert body["income"] == {key: f"{getattr(expected.income, key):.2f}" for key in ZEROS}
        assert body["expense"] == {key: f"{getattr(expected.expense, key):.2f}" for key in ZEROS}
        # Same groups and totals; ties in total are ordered by pt-BR category only in SQL.
        assert sorted((g["type"], g["category"], g["total"]) for g in body["by_category"]) == sorted(
            (g.type, g.category, f"{g.total:.2f}") for g in expected.by_category
        )
    budgets = client.get("/api/budgets", params={"month": "2026-10"}, headers=headers).json()
    assert {b["category"]: b["spent"] for b in budgets} == {
        b["category"]: f"{budget_spent(stored, b['category'], date(2026, 10, 1)):.2f}" for b in budgets
    }


# --- pure rules ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("paid_at", "paid_on"),
    [
        # Midnight in São Paulo is 03:00 UTC: a 00:00 UTC instant would slide back a day.
        (datetime(2026, 10, 22, 2, 59, tzinfo=UTC), date(2026, 10, 21)),
        (paid_at_for(date(2026, 3, 1), SAO_PAULO, NOW), date(2026, 3, 1)),
    ],
)
def test_paid_on_round_trip(paid_at, paid_on):
    assert paid_on_of(paid_at, SAO_PAULO) == paid_on


@pytest.mark.parametrize(
    ("spent", "amount", "expected"),
    [("10", "0", None), ("1", "3", "33.3"), ("1", "1600", "0.1")],
)
def test_percent_used(spent, amount, expected):
    result = percent_used(Decimal(spent), Decimal(amount))
    assert (None if result is None else str(result)) == expected


def test_month_bounds_handle_december_9999():
    assert month_bounds(date(9999, 12, 1)) == (date(9999, 12, 1), date(9999, 12, 31))
