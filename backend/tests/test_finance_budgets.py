from datetime import UTC, datetime

import pytest

from app.core import clock
from app.repositories import budget as budget_repo

URL = "/api/budgets"
NOT_FOUND = "Orçamento não encontrado."
EXISTS = "Já existe orçamento para essa categoria nesse mês."
NOW = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)  # 12:00 of 2026-10-21 in America/Sao_Paulo
READ_FIELDS = {"id", "category", "month", "amount", "spent", "remaining", "percent_used"}


def messages(response) -> list[str]:
    return [error["msg"] for error in response.json()["detail"]]


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch):
    monkeypatch.setattr(clock, "now_utc", lambda: NOW)


@pytest.fixture
def headers(authenticate):
    return authenticate("ana@example.test")[1]


@pytest.fixture
def make(client, headers):
    def _make(
        category: str = "Mercado", amount="500.00", month: str = "2026-10", request_headers=None
    ) -> dict:
        body = {"category": category, "month": month, "amount": amount}
        response = client.post(URL, json=body, headers=request_headers or headers)
        assert response.status_code == 201, response.text
        return response.json()

    return _make


@pytest.fixture
def spend(client, headers):
    def _spend(category: str, amount: str, due: str, type_: str = "expense", paid: bool = False) -> None:
        body = {"type": type_, "amount": amount, "category": category, "due_date": due}
        if paid:
            body["paid_on"] = "2026-10-21"
        assert client.post("/api/transactions", json=body, headers=headers).status_code == 201

    return _spend


def budgets(client, headers, **params) -> list[dict]:
    response = client.get(URL, params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


# --- create --------------------------------------------------------------------------------------


def test_create_reads_back_with_spent(client, headers, make):
    body = make(category="  Mercado ", amount=500)

    assert set(body) == READ_FIELDS
    assert (body["category"], body["month"], body["amount"]) == ("Mercado", "2026-10", "500.00")
    assert (body["spent"], body["remaining"], body["percent_used"]) == ("0.00", "500.00", "0.0")
    assert budgets(client, headers) == [body]  # default month: the current one


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"amount": 12.5}, 'Envie valores em dinheiro como texto (ex.: "12.90").'),
        ({"amount": "-1"}, "O valor deve ser maior ou igual a 0."),
        ({"month": "2026-10-01"}, "Informe um mês válido no formato AAAA-MM."),
        ({"category": ""}, "Informe a categoria."),
    ],
)
def test_create_rejects_invalid_fields(client, headers, payload, message):
    response = client.post(
        URL, json={"category": "Mercado", "month": "2026-10", "amount": "1", **payload}, headers=headers
    )

    assert response.status_code == 422
    assert messages(response) == [message]


@pytest.mark.parametrize("category", ["Mercado", "MERCADO"])
def test_same_category_in_the_same_month_is_409_without_case(client, headers, make, category):
    make("Mercado")

    response = client.post(
        URL, json={"category": category, "month": "2026-10", "amount": "1"}, headers=headers
    )

    assert (response.status_code, response.json()["detail"]) == (409, EXISTS)
    assert make(category, month="2026-11")["month"] == "2026-11"  # another month is fine


# --- spent, remaining, percent -------------------------------------------------------------------


def test_spent_counts_month_expenses_paid_or_not_without_case(client, headers, make, spend):
    make("Mercado", "100.00")
    make("Lazer", "0")
    make("Água", "50")
    spend("mercado", "80.00", "2026-10-01", paid=True)
    spend("MERCADO", "45.50", "2026-10-31")
    spend("Mercado", "999.00", "2026-11-01")  # another month
    spend("Mercado", "999.00", "2026-10-10", type_="income")  # not an expense
    spend("Lazer", "30.00", "2026-10-05")

    listed = {item["category"]: item for item in budgets(client, headers, month="2026-10")}

    assert list(listed) == ["Água", "Lazer", "Mercado"]  # pt-BR order
    assert {key: listed["Mercado"][key] for key in ("spent", "remaining", "percent_used")} == {
        "spent": "125.50",
        "remaining": "-25.50",
        "percent_used": "125.5",
    }
    assert (listed["Lazer"]["remaining"], listed["Lazer"]["percent_used"]) == ("-30.00", None)
    assert (listed["Água"]["spent"], listed["Água"]["percent_used"]) == ("0.00", "0.0")


# --- update and delete ---------------------------------------------------------------------------


def test_patch_changes_only_the_amount(client, headers, make, spend):
    created = make("Mercado", "100")
    spend("Mercado", "25", "2026-10-02")

    response = client.patch(f"{URL}/{created['id']}", json={"amount": "50"}, headers=headers)

    assert response.status_code == 200
    assert (response.json()["amount"], response.json()["percent_used"]) == ("50.00", "50.0")
    rejected = client.patch(f"{URL}/{created['id']}", json={"category": "Lazer"}, headers=headers)
    assert (rejected.status_code, messages(rejected)) == (422, ["Campo não permitido."])


@pytest.mark.parametrize(("method", "body"), [("PATCH", {"amount": "1"}), ("DELETE", None)])
def test_other_users_budget_is_not_found(client, headers, authenticate, make, method, body):
    created = make()
    bia_headers = authenticate("bia@example.test")[1]

    response = client.request(method, f"{URL}/{created['id']}", json=body, headers=bia_headers)

    assert (response.status_code, response.json()["detail"]) == (404, NOT_FOUND)
    assert budgets(client, headers) == [created]
    assert budgets(client, bia_headers) == []


def test_delete_then_not_found(client, headers, make):
    created = make()

    assert client.delete(f"{URL}/{created['id']}", headers=headers).status_code == 204
    response = client.delete(f"{URL}/{created['id']}", headers=headers)
    assert (response.status_code, response.json()["detail"]) == (404, NOT_FOUND)


# --- copy ----------------------------------------------------------------------------------------


def test_copy_skips_categories_the_target_already_has(client, headers, make):
    make("Mercado", "500")
    make("Lazer", "300")
    make("Pets", "0")
    make("LAZER", "999", month="2026-11")

    response = client.post(URL + "/copy", params={"from": "2026-10", "to": "2026-11"}, headers=headers)

    assert response.status_code == 201, response.text
    body = response.json()
    assert [(item["category"], item["month"], item["amount"]) for item in body["created"]] == [
        ("Mercado", "2026-11", "500.00"),
        ("Pets", "2026-11", "0.00"),
    ]
    assert body["skipped"] == ["Lazer"]
    again = client.post(URL + "/copy", params={"from": "2026-10", "to": "2026-11"}, headers=headers)
    assert (again.status_code, again.json()) == (
        200,
        {"created": [], "skipped": ["Lazer", "Mercado", "Pets"]},
    )


@pytest.mark.parametrize(
    "params",
    [{"from": "2026-10", "to": "2026-10"}, {"from": "2026-13", "to": "2026-11"}, {"from": "2026-10"}],
)
def test_copy_rejects_invalid_months(client, headers, params):
    assert client.post(URL + "/copy", params=params, headers=headers).status_code == 422


def test_unique_constraint_is_also_a_409(client, headers, make, monkeypatch):
    """Same spelling slipping past the check (e.g. written by other means): the UNIQUE answers 409."""
    make("Mercado")
    monkeypatch.setattr(budget_repo, "category_exists", lambda *args: False)

    response = client.post(
        URL, json={"category": "Mercado", "month": "2026-10", "amount": "1"}, headers=headers
    )

    assert (response.status_code, response.json()["detail"]) == (409, EXISTS)
