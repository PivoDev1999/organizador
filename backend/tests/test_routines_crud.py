import uuid

import pytest

ROUTINES_URL = "/api/routines"
NOT_FOUND = "Rotina não encontrada."
READ_FIELDS = {
    "id",
    "name",
    "description",
    "frequency",
    "days_of_week",
    "day_of_month",
    "time_of_day",
    "is_active",
    "created_at",
    "updated_at",
}


def routine_url(routine_id) -> str:
    return f"{ROUTINES_URL}/{routine_id}"


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
        payload.setdefault("name", "Rotina")
        payload.setdefault("frequency", "daily")
        response = client.post(ROUTINES_URL, json=payload, headers=headers)
        assert response.status_code == 201, response.text
        return response.json()

    return _make


def messages(response) -> list[str]:
    detail = response.json()["detail"]
    return [detail] if isinstance(detail, str) else [error["msg"] for error in detail]


# --- create ------------------------------------------------------------------------------------


def test_create_daily_routine_with_defaults(client, ana):
    _, headers = ana

    response = client.post(
        ROUTINES_URL, json={"name": "  Passear com a Mel  ", "frequency": "daily"}, headers=headers
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == READ_FIELDS
    assert body["name"] == "Passear com a Mel"
    assert body["description"] is None
    assert body["days_of_week"] is None
    assert body["day_of_month"] is None
    assert body["time_of_day"] is None
    assert body["is_active"] is True
    assert client.get(routine_url(body["id"]), headers=headers).json() == body


def test_create_weekly_normalizes_days(make):
    body = make(name="Reciclável", frequency="weekly", days_of_week=[5, 2, 5], time_of_day="19:30")

    assert body["days_of_week"] == [2, 5]
    assert body["time_of_day"] == "19:30:00"


def test_create_monthly_with_blank_description(make):
    body = make(name="Contas", frequency="monthly", day_of_month=31, description="   ")

    assert body["day_of_month"] == 31
    assert body["description"] is None


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"frequency": "daily", "days_of_week": [1]}, "Rotinas diárias"),
        ({"frequency": "daily", "day_of_month": 3}, "Rotinas diárias"),
        ({"frequency": "weekly"}, "Informe os dias da semana"),
        ({"frequency": "weekly", "days_of_week": []}, "Informe os dias da semana"),
        ({"frequency": "weekly", "days_of_week": [1], "day_of_month": 3}, "Rotinas semanais"),
        ({"frequency": "monthly"}, "Informe o dia do mês"),
        ({"frequency": "monthly", "day_of_month": 3, "days_of_week": [1]}, "Rotinas mensais"),
    ],
)
def test_create_rejects_schedule_incoherent_with_frequency(client, ana, payload, message):
    _, headers = ana

    response = client.post(ROUTINES_URL, json={"name": "X", **payload}, headers=headers)

    assert response.status_code == 422
    assert any(msg.startswith(message) for msg in messages(response))


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "   "},
        {"name": "x" * 201},
        {"frequency": "yearly"},
        {"frequency": "weekly", "days_of_week": [7]},
        {"frequency": "weekly", "days_of_week": ["1"]},
        {"frequency": "weekly", "days_of_week": [True]},
        {"frequency": "monthly", "day_of_month": 0},
        {"frequency": "monthly", "day_of_month": 32},
        {"time_of_day": "7:00"},
        {"time_of_day": "07:00Z"},
        {"time_of_day": "2026-10-21T07:00:00"},
        {"time_of_day": 3600},
        {"time_of_day": "25:00"},
        {"user_id": str(uuid.uuid4())},
        {"is_active": None},
    ],
)
def test_create_rejects_invalid_fields(client, ana, payload):
    _, headers = ana

    response = client.post(ROUTINES_URL, json={"name": "X", "frequency": "daily", **payload}, headers=headers)

    assert response.status_code == 422


def test_validation_message_does_not_echo_input(client, ana):
    _, headers = ana

    response = client.post(
        ROUTINES_URL,
        json={"name": "X", "frequency": "daily", "time_of_day": "segredo-123"},
        headers=headers,
    )

    assert response.status_code == 422
    assert "segredo-123" not in response.text


# --- read / list -------------------------------------------------------------------------------


def test_list_filters_and_sorts(client, ana, make):
    _, headers = ana
    make(name="Faxina", frequency="weekly", days_of_week=[6])
    make(name="banho da Mel", frequency="monthly", day_of_month=1)
    make(name="Água nas plantas", frequency="daily", is_active=False)
    make(name="100%_off", frequency="daily")

    def names(**params) -> list[str]:
        response = client.get(ROUTINES_URL, params=params, headers=headers)
        assert response.status_code == 200, response.text
        return [item["name"] for item in response.json()["items"]]

    assert names() == ["100%_off", "Água nas plantas", "banho da Mel", "Faxina"]
    assert names(sort="-name") == ["Faxina", "banho da Mel", "Água nas plantas", "100%_off"]
    assert names(frequency=["weekly", "monthly"]) == ["banho da Mel", "Faxina"]
    assert names(is_active="false") == ["Água nas plantas"]
    assert names(q="MEL") == ["banho da Mel"]
    assert names(q="%_") == ["100%_off"]
    page = client.get(ROUTINES_URL, params={"limit": 2, "offset": 1}, headers=headers).json()
    assert page["total"] == 4
    assert [item["name"] for item in page["items"]] == ["Água nas plantas", "banho da Mel"]


def test_list_rejects_unknown_sort(client, ana):
    _, headers = ana

    assert client.get(ROUTINES_URL, params={"sort": "time"}, headers=headers).status_code == 422


# --- update ------------------------------------------------------------------------------------


def test_patch_updates_fields(client, ana, make):
    _, headers = ana
    routine = make(name="Louça", description="Antes de dormir", time_of_day="21:00")

    response = client.patch(
        routine_url(routine["id"]),
        json={"name": "Lavar a louça", "description": None, "time_of_day": None, "is_active": False},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Lavar a louça"
    assert body["description"] is None
    assert body["time_of_day"] is None
    assert body["is_active"] is False
    assert body["updated_at"] >= routine["updated_at"]


def test_patch_frequency_change_clears_old_fields(client, ana, make):
    _, headers = ana
    routine = make(frequency="weekly", days_of_week=[1, 3])

    to_monthly = client.patch(
        routine_url(routine["id"]), json={"frequency": "monthly", "day_of_month": 10}, headers=headers
    )
    assert to_monthly.status_code == 200, to_monthly.text
    assert to_monthly.json()["days_of_week"] is None
    assert to_monthly.json()["day_of_month"] == 10

    to_daily = client.patch(routine_url(routine["id"]), json={"frequency": "daily"}, headers=headers)
    assert to_daily.status_code == 200
    assert to_daily.json()["day_of_month"] is None


@pytest.mark.parametrize(
    ("start", "patch", "message"),
    [
        # Frequency change without the fields the new one requires.
        ({"frequency": "daily"}, {"frequency": "weekly"}, "Informe os dias da semana"),
        ({"frequency": "weekly", "days_of_week": [1]}, {"frequency": "monthly"}, "Informe o dia do mês"),
        # Frequency change sending a field the new one does not use.
        ({"frequency": "monthly", "day_of_month": 5}, {"frequency": "daily", "day_of_month": 5}, "Rotinas"),
        # No frequency change, but the result would be incoherent.
        ({"frequency": "weekly", "days_of_week": [1]}, {"days_of_week": None}, "Informe os dias da semana"),
        ({"frequency": "weekly", "days_of_week": [1]}, {"days_of_week": []}, "Informe os dias da semana"),
        ({"frequency": "weekly", "days_of_week": [1]}, {"day_of_month": 3}, "Rotinas semanais"),
        ({"frequency": "monthly", "day_of_month": 5}, {"day_of_month": None}, "Informe o dia do mês"),
        ({"frequency": "daily"}, {"days_of_week": [2]}, "Rotinas diárias"),
    ],
)
def test_patch_rejects_incoherent_schedule(client, ana, make, start, patch, message):
    _, headers = ana
    routine = make(**start)

    response = client.patch(routine_url(routine["id"]), json=patch, headers=headers)

    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"].startswith(message)
    # Nothing changed.
    assert client.get(routine_url(routine["id"]), headers=headers).json() == routine


@pytest.mark.parametrize("field", ["name", "frequency", "is_active"])
def test_patch_rejects_null_for_required_fields(client, ana, make, field):
    _, headers = ana
    routine = make()

    response = client.patch(routine_url(routine["id"]), json={field: None}, headers=headers)

    assert response.status_code == 422


def test_noop_patch_keeps_updated_at(client, ana, make):
    _, headers = ana
    routine = make(name="Igual")

    response = client.patch(routine_url(routine["id"]), json={"name": "Igual"}, headers=headers)

    assert response.status_code == 200
    assert response.json() == routine


# --- delete ------------------------------------------------------------------------------------


def test_delete_removes_routine_and_logs(client, ana, make):
    _, headers = ana
    routine = make()
    assert client.post(f"{routine_url(routine['id'])}/logs", json={}, headers=headers).status_code == 201

    response = client.delete(routine_url(routine["id"]), headers=headers)

    assert response.status_code == 204
    assert client.get(routine_url(routine["id"]), headers=headers).status_code == 404
    assert client.get(f"{routine_url(routine['id'])}/logs", headers=headers).status_code == 404


# --- isolation and auth ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [
        ("GET", "", None),
        ("PATCH", "", {"name": "Invasão"}),
        ("DELETE", "", None),
        ("GET", "/logs", None),
        ("POST", "/logs", {}),
        ("DELETE", "/logs/2026-10-01", None),
    ],
)
def test_other_users_routine_is_not_found(client, ana, bia, make, method, suffix, body):
    routine = make()
    _, bia_headers = bia

    response = client.request(method, routine_url(routine["id"]) + suffix, json=body, headers=bia_headers)

    assert response.status_code == 404
    assert response.json() == {"detail": NOT_FOUND}


def test_list_and_today_only_show_own_routines(client, ana, bia, make):
    make(name="Da Ana")
    _, bia_headers = bia

    assert client.get(ROUTINES_URL, headers=bia_headers).json()["total"] == 0
    assert client.get(f"{ROUTINES_URL}/today", headers=bia_headers).json() == []


def test_unknown_routine_is_not_found(client, ana):
    _, headers = ana

    response = client.get(routine_url(uuid.uuid4()), headers=headers)

    assert response.status_code == 404
    assert response.json() == {"detail": NOT_FOUND}


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", ROUTINES_URL),
        ("POST", ROUTINES_URL),
        ("GET", f"{ROUTINES_URL}/today"),
        ("GET", routine_url(uuid.uuid4())),
        ("PATCH", routine_url(uuid.uuid4())),
        ("DELETE", routine_url(uuid.uuid4())),
        ("GET", f"{routine_url(uuid.uuid4())}/logs"),
        ("POST", f"{routine_url(uuid.uuid4())}/logs"),
        ("DELETE", f"{routine_url(uuid.uuid4())}/logs/2026-10-01"),
    ],
)
def test_requires_authentication(client, method, path):
    response = client.request(method, path)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
