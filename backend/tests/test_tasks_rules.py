"""HTTP-level business rules of /api/tasks: completed_at, updated_at, isolation and authentication."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from app.core import clock
from tests.helpers import TEST_PASSWORD, auth_header, login, make_token

TASKS_URL = "/api/tasks"
NOT_FOUND = "Tarefa não encontrada."
READ_FIELDS = {
    "id",
    "title",
    "description",
    "status",
    "priority",
    "due_date",
    "completed_at",
    "created_at",
    "updated_at",
}
OLD = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)
T0 = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
T1 = datetime(2026, 10, 19, 15, 0, tzinfo=UTC)


def task_url(task_id) -> str:
    return f"{TASKS_URL}/{task_id}"


def parse_dt(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


@pytest.fixture
def ana(authenticate):
    return authenticate("ana@example.test")


@pytest.fixture
def bia(authenticate):
    return authenticate("bia@example.test")


@pytest.fixture
def freeze_now(monkeypatch):
    def _freeze(moment: datetime) -> None:
        monkeypatch.setattr(clock, "now_utc", lambda: moment)

    return _freeze


@pytest.fixture
def old_task(ana, create_task):
    """Ana's task whose timestamps are far in the past, so any trigger-driven update is visible."""

    def _make(**fields):
        if fields.get("status") == "done":
            fields.setdefault("completed_at", T0)
        return create_task(ana[0], fields.pop("title", "Antiga"), created_at=OLD, updated_at=OLD, **fields)

    return _make


# --- completed_at through the API --------------------------------------------------------------


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        ("todo", "done", T1),
        ("doing", "done", T1),
        ("done", "todo", None),
        ("done", "doing", None),
        ("done", "done", T0),
    ],
    ids=["todo-done", "doing-done", "done-todo", "done-doing", "done-done"],
)
def test_patch_status_transition_completed_at(client, ana, old_task, freeze_now, before, after, expected):
    task = old_task(status=before)
    freeze_now(T1)

    response = client.patch(task_url(task.id), json={"status": after}, headers=ana[1])

    assert response.status_code == 200
    assert parse_dt(response.json()["completed_at"]) == expected
    assert parse_dt(client.get(task_url(task.id), headers=ana[1]).json()["completed_at"]) == expected


def test_patch_title_of_done_task_keeps_completed_at(client, ana, old_task, freeze_now):
    task = old_task(status="done")
    freeze_now(T1)

    body = client.patch(task_url(task.id), json={"title": "Renomeada"}, headers=ana[1]).json()

    assert body["title"] == "Renomeada"
    assert body["status"] == "done"
    assert parse_dt(body["completed_at"]) == T0


def test_create_done_task_completed_at_matches_frozen_clock(client, ana, freeze_now):
    freeze_now(T1)

    body = client.post(TASKS_URL, json={"title": "Feita", "status": "done"}, headers=ana[1]).json()

    assert parse_dt(body["completed_at"]) == T1
    assert parse_dt(client.get(task_url(body["id"]), headers=ana[1]).json()["completed_at"]) == T1


@pytest.mark.parametrize("status", ["todo", "doing"])
def test_create_open_task_has_no_completed_at(client, ana, freeze_now, status):
    freeze_now(T1)

    body = client.post(TASKS_URL, json={"title": "Aberta", "status": status}, headers=ana[1]).json()

    assert body["completed_at"] is None


# --- updated_at --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"title": "Antiga"},
        {"title": "  Antiga  "},
        {"status": "todo", "priority": "medium"},
        {"description": None, "due_date": None},
        {"description": "   "},
    ],
    ids=["empty", "same-title", "same-title-untrimmed", "same-enums", "null-on-null", "blank-on-null"],
)
def test_patch_without_real_change_keeps_updated_at(client, ana, old_task, payload):
    task = old_task()

    response = client.patch(task_url(task.id), json=payload, headers=ana[1])

    assert response.status_code == 200
    assert parse_dt(response.json()["updated_at"]) == OLD
    assert parse_dt(client.get(task_url(task.id), headers=ana[1]).json()["updated_at"]) == OLD


@pytest.mark.parametrize(
    "payload",
    [
        {"title": "Nova"},
        {"description": "Agora tem"},
        {"status": "doing"},
        {"priority": "high"},
        {"due_date": "2026-12-01"},
    ],
    ids=["title", "description", "status", "priority", "due-date"],
)
def test_patch_with_change_bumps_updated_at_and_keeps_created_at(client, ana, old_task, payload):
    task = old_task()

    response = client.patch(task_url(task.id), json=payload, headers=ana[1])

    body = response.json()
    assert parse_dt(body["updated_at"]) > OLD
    assert parse_dt(body["created_at"]) == OLD
    # The response reflects the stored row, not a stale in-memory value.
    assert client.get(task_url(task.id), headers=ana[1]).json() == body


def test_failed_patch_keeps_updated_at(client, ana, old_task):
    task = old_task()

    response = client.patch(task_url(task.id), json={"title": "Nova", "status": "archived"}, headers=ana[1])

    assert response.status_code == 422
    stored = client.get(task_url(task.id), headers=ana[1]).json()
    assert (stored["title"], parse_dt(stored["updated_at"])) == ("Antiga", OLD)


# --- 404 ---------------------------------------------------------------------------------------


def test_patch_missing_task_is_not_found(client, ana):
    response = client.patch(task_url(uuid.uuid4()), json={"title": "X"}, headers=ana[1])

    assert response.status_code == 404
    assert response.json() == {"detail": NOT_FOUND}


def test_deleting_twice_returns_404_the_second_time(client, ana, create_task):
    task = create_task(ana[0])

    assert client.delete(task_url(task.id), headers=ana[1]).status_code == 204
    second = client.delete(task_url(task.id), headers=ana[1])

    assert second.status_code == 404
    assert second.json() == {"detail": NOT_FOUND}
    assert client.patch(task_url(task.id), json={"title": "X"}, headers=ana[1]).status_code == 404


def test_uppercase_uuid_in_path_finds_the_task(client, ana, create_task):
    task = create_task(ana[0])

    response = client.get(task_url(str(task.id).upper()), headers=ana[1])

    assert response.status_code == 200
    assert response.json()["id"] == str(task.id)


# --- isolation between users -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "payload"),
    [
        ("GET", None),
        ("PATCH", {"title": "Invadida", "status": "done", "priority": "low", "due_date": None}),
        ("PATCH", {}),
        ("DELETE", None),
    ],
    ids=["get", "patch", "empty-patch", "delete"],
)
def test_other_users_task_looks_missing_and_stays_intact(client, ana, bia, create_task, method, payload):
    bias_task = create_task(
        bia[0], "Da Bia", description="Privada", priority="high", due_date=date(2026, 11, 1)
    )
    snapshot = client.get(task_url(bias_task.id), headers=bia[1]).json()

    response = client.request(method, task_url(bias_task.id), json=payload, headers=ana[1])
    missing = client.request(method, task_url(uuid.uuid4()), json=payload, headers=ana[1])

    assert response.status_code == 404
    # Indistinguishable from a task that does not exist: no way to probe other users' ids.
    assert response.json() == missing.json() == {"detail": NOT_FOUND}
    assert client.get(task_url(bias_task.id), headers=bia[1]).json() == snapshot


def test_owner_can_still_use_task_after_another_user_tried(client, ana, bia, create_task):
    bias_task = create_task(bia[0], "Da Bia")
    client.delete(task_url(bias_task.id), headers=ana[1])

    response = client.patch(task_url(bias_task.id), json={"title": "Editada"}, headers=bia[1])

    assert response.status_code == 200
    assert response.json()["title"] == "Editada"


def test_created_task_belongs_to_the_token_owner(client, ana, bia):
    body = client.post(TASKS_URL, json={"title": "Da Ana"}, headers=ana[1]).json()

    assert client.get(task_url(body["id"]), headers=ana[1]).status_code == 200
    assert client.get(task_url(body["id"]), headers=bia[1]).status_code == 404


# --- response shape ----------------------------------------------------------------------------


def test_every_response_has_only_public_fields(client, ana):
    headers = ana[1]
    created = client.post(TASKS_URL, json={"title": "X"}, headers=headers).json()
    patched = client.patch(task_url(created["id"]), json={"title": "Y"}, headers=headers).json()
    fetched = client.get(task_url(created["id"]), headers=headers).json()
    listed = client.get(TASKS_URL, headers=headers).json()["items"][0]

    for body in (created, patched, fetched, listed):
        assert set(body) == READ_FIELDS
        assert "user_id" not in body


def test_timestamps_are_timezone_aware(client, ana):
    body = client.post(TASKS_URL, json={"title": "X", "status": "done"}, headers=ana[1]).json()

    for field in ("created_at", "updated_at", "completed_at"):
        assert parse_dt(body[field]).utcoffset() is not None, field


# --- authentication ----------------------------------------------------------------------------


ENDPOINTS = [
    ("GET", TASKS_URL),
    ("POST", TASKS_URL),
    ("GET", "{task}"),
    ("PATCH", "{task}"),
    ("DELETE", "{task}"),
]
ENDPOINT_IDS = ["list", "create", "get", "patch", "delete"]


def _expired(user) -> dict:
    return auth_header(make_token(user.id, now=datetime.now(UTC) - timedelta(hours=1)))


INVALID_AUTH = [
    lambda user: {},
    lambda user: auth_header("not-a-jwt"),
    lambda user: auth_header(make_token(user.id, secret="x" * 32)),
    _expired,
    lambda user: auth_header(make_token(uuid.uuid4())),
    lambda user: {"Authorization": f"Basic {make_token(user.id)}"},
]
INVALID_AUTH_IDS = ["missing", "garbage", "wrong-key", "expired", "unknown-user", "wrong-scheme"]


@pytest.mark.parametrize(("method", "path"), ENDPOINTS, ids=ENDPOINT_IDS)
@pytest.mark.parametrize("make_headers", INVALID_AUTH, ids=INVALID_AUTH_IDS)
def test_task_endpoints_reject_invalid_tokens(client, create_user, create_task, method, path, make_headers):
    user = create_user()
    task = create_task(user, "Protegida")
    url = task_url(task.id) if path == "{task}" else path

    response = client.request(method, url, json={"title": "X"}, headers=make_headers(user))

    assert response.status_code == 401
    assert response.json() == {"detail": "Não autenticado."}
    assert response.headers["WWW-Authenticate"] == "Bearer"
    # Nothing changed for the real owner.
    assert (
        client.get(task_url(task.id), headers=auth_header(make_token(user.id))).json()["title"] == "Protegida"
    )


@pytest.mark.parametrize(("method", "path"), ENDPOINTS, ids=ENDPOINT_IDS)
def test_task_endpoints_reject_inactive_user(client, create_user, create_task, method, path):
    user = create_user(is_active=False)
    task = create_task(user)
    url = task_url(task.id) if path == "{task}" else path

    response = client.request(method, url, json={"title": "X"}, headers=auth_header(make_token(user.id)))

    assert response.status_code == 401
    assert response.json() == {"detail": "Não autenticado."}


@pytest.mark.parametrize(("method", "path"), ENDPOINTS, ids=ENDPOINT_IDS)
def test_task_endpoints_reject_user_deactivated_after_login(
    client, db_session, create_user, create_task, method, path
):
    user = create_user("ana@example.test")
    task = create_task(user)
    headers = auth_header(login(client, "ana@example.test", TEST_PASSWORD).json()["access_token"])
    assert client.get(TASKS_URL, headers=headers).status_code == 200
    user.is_active = False
    db_session.commit()
    url = task_url(task.id) if path == "{task}" else path

    response = client.request(method, url, json={"title": "X"}, headers=headers)

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("method", "url", "kwargs"),
    [
        ("POST", TASKS_URL, {"content": b"{broken"}),
        ("POST", TASKS_URL, {"json": {"title": ""}}),
        ("GET", task_url("not-a-uuid"), {}),
        ("PATCH", task_url("not-a-uuid"), {"json": {"status": "x"}}),
        ("GET", TASKS_URL, {"params": {"limit": 0, "sort": "x"}}),
    ],
    ids=["broken-json", "invalid-body", "bad-path-id", "bad-path-and-body", "bad-query"],
)
def test_authentication_is_checked_before_validation(client, method, url, kwargs):
    response = client.request(method, url, **kwargs)

    assert response.status_code == 401
    assert response.json() == {"detail": "Não autenticado."}
