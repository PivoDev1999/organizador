import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from app.core import clock

URL = "/api/transactions"
NOT_FOUND = "Transação não encontrada."
TODAY = date(2026, 10, 21)
NOW = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)  # 12:00 of 2026-10-21 in America/Sao_Paulo
# 23:30 of the 21st in São Paulo, already the 22nd in UTC.
LATE_NIGHT = datetime(2026, 10, 22, 2, 30, tzinfo=UTC)
READ_FIELDS = {
    "id",
    "type",
    "amount",
    "category",
    "description",
    "due_date",
    "pet_id",
    "paid_at",
    "paid_on",
    "overdue",
    "created_at",
    "updated_at",
}


def day(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


def tx_url(transaction_id, suffix: str = "") -> str:
    return f"{URL}/{transaction_id}{suffix}"


def messages(response) -> list[str]:
    return [error["msg"] for error in response.json()["detail"]]


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
    def _make(
        category: str = "Moradia", amount="100.00", due: int = 0, request_headers=None, **payload
    ) -> dict:
        body = {"type": "expense", "amount": amount, "category": category, "due_date": day(due), **payload}
        response = client.post(URL, json=body, headers=request_headers or headers)
        assert response.status_code == 201, response.text
        return response.json()

    return _make


@pytest.fixture
def make_pet(client):
    def _make(request_headers: dict, name: str = "Mel") -> str:
        response = client.post(
            "/api/pets", json={"name": name, "species": "Cachorro"}, headers=request_headers
        )
        assert response.status_code == 201, response.text
        return response.json()["id"]

    return _make


def listed(client, headers, **params) -> list[str]:
    response = client.get(URL, params=params, headers=headers)
    assert response.status_code == 200, response.text
    return [item["description"] for item in response.json()["items"]]


# --- create --------------------------------------------------------------------------------------


def test_create_normalizes_and_reads_back(client, headers):
    payload = {
        "type": "expense",
        "amount": "245.9",
        "category": "  Moradia ",
        "description": "   ",
        "due_date": day(5),
    }

    response = client.post(URL, json=payload, headers=headers)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == READ_FIELDS
    assert (body["amount"], body["category"], body["description"]) == ("245.90", "Moradia", None)
    assert (body["paid_at"], body["paid_on"], body["overdue"], body["pet_id"]) == (None, None, False, None)
    assert client.get(tx_url(body["id"]), headers=headers).json() == body


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"amount": 12.9}, 'Envie valores em dinheiro como texto (ex.: "12.90").'),
        ({"amount": 0}, "O valor deve ser maior que 0."),
        ({"category": "  "}, "Informe a categoria."),
        ({"paid_at": "2026-10-21T12:00:00Z"}, "Campo não permitido."),
        ({"due_date": "1999-12-31"}, "O vencimento deve ser a partir de 01/01/2000."),
    ],
)
def test_create_rejects_invalid_fields(client, headers, payload, message):
    body = {"type": "expense", "amount": "10", "category": "Moradia", "due_date": day(0), **payload}

    response = client.post(URL, json=body, headers=headers)

    assert response.status_code == 422
    assert messages(response) == [message]
    assert client.get(URL, headers=headers).json()["total"] == 0


@pytest.mark.parametrize(
    ("now", "paid_on", "status"),
    [
        # 23:30 of the 21st in São Paulo: the 22nd is still the future, even though UTC is there.
        (LATE_NIGHT, "2026-10-22", 422),
        (datetime(2026, 10, 22, 3, 0, tzinfo=UTC), "2026-10-22", 201),
    ],
)
def test_paid_on_cannot_be_in_the_future_in_the_app_timezone(
    client, headers, monkeypatch, now, paid_on, status
):
    monkeypatch.setattr(clock, "now_utc", lambda: now)
    body = {"type": "expense", "amount": "10", "category": "Moradia", "due_date": day(0), "paid_on": paid_on}

    response = client.post(URL, json=body, headers=headers)

    assert response.status_code == status, response.text
    if status == 422:
        assert messages(response) == ["A data de pagamento não pode ser no futuro."]
    else:
        assert response.json()["paid_on"] == paid_on


@pytest.mark.parametrize(
    ("now", "paid_on", "paid_at"),
    [
        # Today: the current instant (here 23:30 of the 21st in São Paulo, 02:30 of the 22nd in UTC).
        (LATE_NIGHT, "2026-10-21", "2026-10-22T02:30:00Z"),
        # Another day: noon in São Paulo (UTC-3), which never slides to a neighbouring day.
        (NOW, "2026-10-01", "2026-10-01T15:00:00Z"),
    ],
)
def test_paid_on_becomes_paid_at(client, headers, monkeypatch, now, paid_on, paid_at):
    monkeypatch.setattr(clock, "now_utc", lambda: now)
    body = {"type": "income", "amount": "10", "category": "Salário", "due_date": day(0), "paid_on": paid_on}

    created = client.post(URL, json=body, headers=headers).json()

    assert datetime.fromisoformat(created["paid_at"]) == datetime.fromisoformat(paid_at)
    assert (created["paid_on"], created["overdue"]) == (paid_on, False)


@pytest.mark.parametrize("endpoint", ["create", "pay"])
def test_paid_on_before_2000_is_422_even_in_a_utc_plus_13_zone(
    client, headers, make, override_settings, endpoint
):
    """Noon of 0001-01-01 in Pacific/Apia is before datetime's minimum in UTC: it must be a 422, not a 500."""
    override_settings(app_timezone="Pacific/Apia")
    if endpoint == "create":
        body = {
            "type": "expense",
            "amount": "10",
            "category": "Moradia",
            "due_date": day(0),
            "paid_on": "0001-01-01",
        }
        response = client.post(URL, json=body, headers=headers)
    else:
        response = client.post(tx_url(make()["id"], "/pay"), json={"paid_on": "0001-01-01"}, headers=headers)

    assert response.status_code == 422
    assert messages(response) == ["A data de pagamento deve ser a partir de 01/01/2000."]


def test_pet_of_someone_else_is_422(client, headers, bia, make_pet):
    pet_id = make_pet(bia[1])
    body = {"type": "expense", "amount": "10", "category": "Pets", "due_date": day(0), "pet_id": pet_id}

    response = client.post(URL, json=body, headers=headers)

    assert response.status_code == 422
    assert messages(response) == ["Pet não encontrado."]


# --- update and delete ---------------------------------------------------------------------------


def test_patch_changes_only_sent_fields_and_clears_nullable_ones(client, headers, make, make_pet):
    pet_id = make_pet(headers)
    created = make(description="Ração", pet_id=pet_id)

    response = client.patch(
        tx_url(created["id"]), json={"amount": 80, "category": "Pets", "pet_id": None}, headers=headers
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["amount"], body["category"], body["pet_id"], body["description"]) == (
        "80.00",
        "Pets",
        None,
        "Ração",
    )
    relinked = client.patch(
        tx_url(created["id"]), json={"pet_id": pet_id, "description": ""}, headers=headers
    )
    assert (relinked.json()["pet_id"], relinked.json()["description"]) == (pet_id, None)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"amount": None}, "Este campo não pode ser nulo."),
        ({"paid_on": day(0)}, "Campo não permitido."),
    ],
)
def test_patch_rejects_null_required_fields_and_payment_fields(client, headers, make, payload, message):
    created = make()

    response = client.patch(tx_url(created["id"]), json=payload, headers=headers)

    assert response.status_code == 422
    assert messages(response) == [message]


def test_patch_with_someone_elses_pet_is_422_and_keeps_the_link(client, headers, bia, make, make_pet):
    pet_id = make_pet(headers)
    created = make(pet_id=pet_id)

    response = client.patch(tx_url(created["id"]), json={"pet_id": make_pet(bia[1], "Rex")}, headers=headers)

    assert response.status_code == 422
    assert client.get(tx_url(created["id"]), headers=headers).json()["pet_id"] == pet_id


def test_delete_then_not_found(client, headers, make):
    created = make()

    assert client.delete(tx_url(created["id"]), headers=headers).status_code == 204
    response = client.get(tx_url(created["id"]), headers=headers)
    assert (response.status_code, response.json()["detail"]) == (404, NOT_FOUND)


def test_deleting_the_pet_keeps_the_expense_without_it(client, headers, make, make_pet):
    pet_id = make_pet(headers)
    created = make(pet_id=pet_id)

    assert client.delete(f"/api/pets/{pet_id}", headers=headers).status_code == 204
    assert client.get(tx_url(created["id"]), headers=headers).json()["pet_id"] is None


# --- pay and unpay -------------------------------------------------------------------------------


def test_pay_defaults_to_today_and_unpay_reverts(client, headers, make):
    created = make(due=-3)
    assert created["overdue"] is True

    paid = client.post(tx_url(created["id"], "/pay"), headers=headers)

    assert paid.status_code == 200, paid.text
    assert (paid.json()["paid_on"], paid.json()["overdue"]) == (TODAY.isoformat(), False)
    assert datetime.fromisoformat(paid.json()["paid_at"]) == NOW
    unpaid = client.post(tx_url(created["id"], "/unpay"), headers=headers)
    assert unpaid.status_code == 200
    assert (unpaid.json()["paid_at"], unpaid.json()["paid_on"], unpaid.json()["overdue"]) == (
        None,
        None,
        True,
    )


@pytest.mark.parametrize(
    ("paid_on", "status", "expected"),
    [
        ("2026-10-02", 200, "2026-10-02"),
        ("2026-10-22", 422, None),
    ],
)
def test_pay_with_a_date(client, headers, make, paid_on, status, expected):
    created = make()

    response = client.post(tx_url(created["id"], "/pay"), json={"paid_on": paid_on}, headers=headers)

    assert response.status_code == status, response.text
    stored = client.get(tx_url(created["id"]), headers=headers).json()
    assert stored["paid_on"] == expected


def test_pay_and_unpay_conflicts(client, headers, make):
    pending = make()
    paid = make(paid_on=day(0))

    unpay = client.post(tx_url(pending["id"], "/unpay"), headers=headers)
    pay = client.post(tx_url(paid["id"], "/pay"), headers=headers)

    assert (unpay.status_code, unpay.json()["detail"]) == (409, "Transação não está paga.")
    assert (pay.status_code, pay.json()["detail"]) == (409, "Transação já paga.")


# --- isolation and auth --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [
        ("GET", "", None),
        ("PATCH", "", {"amount": "1"}),
        ("DELETE", "", None),
        ("POST", "/pay", None),
    ],
)
def test_other_users_transaction_is_not_found_and_untouched(client, headers, bia, make, method, suffix, body):
    created = make(paid_on=day(0))

    response = client.request(method, tx_url(created["id"], suffix), json=body, headers=bia[1])

    assert (response.status_code, response.json()["detail"]) == (404, NOT_FOUND)
    assert client.get(tx_url(created["id"]), headers=headers).json() == created
    assert client.get(URL, headers=bia[1]).json()["total"] == 0


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", URL),
        ("POST", "/api/budgets/copy?from=2026-10&to=2026-11"),
    ],
)
def test_finance_endpoints_require_authentication(client, method, path):
    assert client.request(method, path).status_code == 401


# --- list filters --------------------------------------------------------------------------------


@pytest.fixture
def ledger(make, make_pet, headers):
    """Seven transactions around 2026-10-21 (today). Descriptions identify them."""
    pet_id = make_pet(headers)
    make("Moradia", "1800", 10, description="Aluguel")
    make("Moradia", "245.90", -1, description="Luz atrasada")
    make("mercado", "300", -2, description="Feira 100%", paid_on=day(-2))
    make("MERCADO", "50", 0, description="Padaria hoje")
    make("Pets", "95", -40, description="Vacina", pet_id=pet_id)
    make("Salário", "6500", -20, type="income", description="Salário", paid_on=day(-20))
    make("Íntimo", "20", 12, description="Ícone")
    return pet_id


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({}, ["Vacina", "Salário", "Feira 100%", "Luz atrasada", "Padaria hoje", "Aluguel", "Ícone"]),
        ({"status": "pending"}, ["Vacina", "Luz atrasada", "Padaria hoje", "Aluguel", "Ícone"]),
        ({"status": "overdue"}, ["Vacina", "Luz atrasada"]),
        ({"status": ["overdue", "paid"]}, ["Vacina", "Salário", "Feira 100%", "Luz atrasada"]),
        ({"type": "income"}, ["Salário"]),
        ({"category": ["Mercado"]}, ["Feira 100%", "Padaria hoje"]),
        ({"category": ["íntimo", "  "]}, ["Ícone"]),
        ({"month": "2026-09"}, ["Vacina"]),
        ({"due_from": day(-2), "due_to": day(0)}, ["Feira 100%", "Luz atrasada", "Padaria hoje"]),
        ({"q": "100%"}, ["Feira 100%"]),
        ({"sort": "-amount", "limit": 3}, ["Salário", "Aluguel", "Feira 100%"]),
    ],
)
def test_list_filters_and_sorts(client, headers, ledger, params, expected):
    assert listed(client, headers, **params) == expected


def test_list_filters_by_pet(client, headers, ledger):
    assert listed(client, headers, pet_id=ledger) == ["Vacina"]
    assert listed(client, headers, pet_id=str(uuid.uuid4())) == []


def test_overdue_follows_the_app_timezone(client, headers, monkeypatch, make):
    make("Moradia", due=0, description="Vence hoje")
    monkeypatch.setattr(clock, "now_utc", lambda: LATE_NIGHT)  # still the 21st in São Paulo

    assert listed(client, headers, status="overdue") == []
    monkeypatch.setattr(clock, "now_utc", lambda: LATE_NIGHT + timedelta(hours=1))  # 00:30 of the 22nd
    assert listed(client, headers, status="overdue") == ["Vence hoje"]


@pytest.mark.parametrize(
    "params",
    [
        {"month": "2026-10", "due_from": "2026-10-01"},
        {"due_from": "2026-10-10", "due_to": "2026-10-09"},
    ],
)
def test_list_rejects_invalid_query(client, headers, params):
    assert client.get(URL, params=params, headers=headers).status_code == 422


# --- upcoming ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("within", "expected"),
    [
        (0, [("Vacina", True), ("Luz atrasada", True), ("Padaria hoje", False)]),
        (
            365,
            [
                ("Vacina", True),
                ("Luz atrasada", True),
                ("Padaria hoje", False),
                ("Aluguel", False),
                ("Ícone", False),
            ],
        ),
    ],
)
def test_upcoming_lists_pending_expenses_in_the_window(client, headers, ledger, make, within, expected):
    make("Salário", "10", 1, type="income", description="Receita futura")

    response = client.get(f"{URL}/upcoming", params={"within": within}, headers=headers)

    assert response.status_code == 200
    assert [(item["description"], item["overdue"]) for item in response.json()] == expected


def test_upcoming_window_is_validated(client, headers):
    assert client.get(f"{URL}/upcoming", params={"within": 366}, headers=headers).status_code == 422
