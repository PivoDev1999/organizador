import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event

from app.core import clock
from app.models import Task

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
T1 = datetime(2026, 10, 19, 15, 0, tzinfo=UTC)


def task_url(task_id) -> str:
    return f"{TASKS_URL}/{task_id}"


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


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


# --- create ------------------------------------------------------------------------------------


def test_create_task_with_defaults(client, ana):
    _, headers = ana

    response = client.post(TASKS_URL, json={"title": "  Trocar a lâmpada  "}, headers=headers)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == READ_FIELDS
    assert body["title"] == "Trocar a lâmpada"
    assert body["description"] is None
    assert body["status"] == "todo"
    assert body["priority"] == "medium"
    assert body["due_date"] is None
    assert body["completed_at"] is None
    # Committed: visible to the next request.
    assert client.get(task_url(body["id"]), headers=headers).json() == body


def test_create_task_with_all_fields(client, ana):
    user, headers = ana
    payload = {
        "title": "Levar o carro na revisão",
        "description": "Ligar antes.",
        "status": "doing",
        "priority": "high",
        "due_date": "2026-11-01",
    }

    response = client.post(TASKS_URL, json=payload, headers=headers)

    assert response.status_code == 201
    assert {key: response.json()[key] for key in payload} == payload


def test_create_done_task_fills_completed_at(client, ana, freeze_now):
    _, headers = ana
    freeze_now(T1)

    body = client.post(TASKS_URL, json={"title": "Feita", "status": "done"}, headers=headers).json()

    assert parse_dt(body["completed_at"]) == T1


def test_create_task_blank_description_becomes_null(client, ana):
    _, headers = ana

    body = client.post(TASKS_URL, json={"title": "X", "description": "   "}, headers=headers).json()

    assert body["description"] is None


@pytest.mark.parametrize(
    ("payload", "loc", "message"),
    [
        ({}, ["body", "title"], None),
        ({"title": "   "}, ["body", "title"], "Informe o título."),
        ({"title": "a" * 201}, ["body", "title"], "O título deve ter no máximo 200 caracteres."),
        ({"title": "a\x00b"}, ["body", "title"], "O texto não pode conter o caractere nulo (\\x00)."),
        (
            {"title": "X", "description": "a" * 5001},
            ["body", "description"],
            "A descrição deve ter no máximo 5000 caracteres.",
        ),
        ({"title": "X", "status": "archived"}, ["body", "status"], None),
        ({"title": "X", "priority": "urgent"}, ["body", "priority"], None),
        ({"title": "X", "due_date": "amanhã"}, ["body", "due_date"], None),
        ({"title": "X", "completed_at": "2026-01-01T00:00:00Z"}, ["body", "completed_at"], None),
        ({"title": "X", "user_id": str(uuid.uuid4())}, ["body", "user_id"], None),
        ({"title": "X", "id": str(uuid.uuid4())}, ["body", "id"], None),
    ],
    ids=[
        "missing-title",
        "blank-title",
        "long-title",
        "nul-in-title",
        "long-description",
        "invalid-status",
        "invalid-priority",
        "invalid-date",
        "extra-completed-at",
        "extra-user-id",
        "extra-id",
    ],
)
def test_create_task_validation(client, ana, payload, loc, message):
    _, headers = ana

    response = client.post(TASKS_URL, json=payload, headers=headers)

    assert response.status_code == 422
    errors = response.json()["detail"]
    assert [error["loc"] for error in errors] == [loc]
    if message is not None:
        assert errors[0]["msg"] == message
    assert "input" not in errors[0]


def test_title_with_exactly_200_characters_is_accepted(client, ana):
    _, headers = ana

    response = client.post(TASKS_URL, json={"title": "a" * 200}, headers=headers)

    assert response.status_code == 201


# --- read --------------------------------------------------------------------------------------


def test_get_own_task(client, ana, create_task):
    user, headers = ana
    task = create_task(user, "Minha tarefa")

    response = client.get(task_url(task.id), headers=headers)

    assert response.status_code == 200
    assert response.json()["id"] == str(task.id)
    assert "user_id" not in response.json()


def test_get_task_of_another_user_is_not_found(client, ana, bia, create_task):
    _, headers = ana
    other_task = create_task(bia[0], "Da Bia")

    response = client.get(task_url(other_task.id), headers=headers)

    assert response.status_code == 404
    assert response.json()["detail"] == NOT_FOUND


def test_get_missing_task_is_not_found(client, ana):
    response = client.get(task_url(uuid.uuid4()), headers=ana[1])

    assert response.status_code == 404
    assert response.json()["detail"] == NOT_FOUND


@pytest.mark.parametrize("method", ["GET", "PATCH", "DELETE"])
def test_non_uuid_id_is_rejected(client, ana, method):
    response = client.request(method, task_url("not-a-uuid"), json={}, headers=ana[1])

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["path", "task_id"]


# --- update ------------------------------------------------------------------------------------


def test_patch_changes_only_sent_fields(client, ana, create_task):
    user, headers = ana
    task = create_task(user, "Antigo", description="Desc", priority="high", due_date=T1.date())

    response = client.patch(task_url(task.id), json={"title": " Novo "}, headers=headers)

    assert response.status_code == 200
    body = client.get(task_url(task.id), headers=headers).json()
    assert body["title"] == "Novo"
    assert body["description"] == "Desc"
    assert body["priority"] == "high"
    assert body["status"] == "todo"
    assert body["due_date"] == T1.date().isoformat()


@pytest.mark.parametrize("field", ["description", "due_date"])
def test_patch_null_clears_nullable_fields(client, ana, create_task, field):
    user, headers = ana
    task = create_task(user, description="Desc", due_date=T1.date())

    response = client.patch(task_url(task.id), json={field: None}, headers=headers)

    assert response.status_code == 200
    assert client.get(task_url(task.id), headers=headers).json()[field] is None


def test_patch_blank_description_clears_it(client, ana, create_task):
    user, headers = ana
    task = create_task(user, description="Desc")

    assert (
        client.patch(task_url(task.id), json={"description": " "}, headers=headers).json()["description"]
        is None
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"title": None},
        {"title": ""},
        {"status": None},
        {"priority": None},
        {"status": "archived"},
        {"completed_at": "2026-01-01T00:00:00Z"},
        {"user_id": str(uuid.uuid4())},
    ],
    ids=[
        "null-title",
        "blank-title",
        "null-status",
        "null-priority",
        "bad-status",
        "completed-at",
        "user-id",
    ],
)
def test_patch_validation(client, ana, create_task, payload):
    user, headers = ana
    task = create_task(user, "Intacta")

    response = client.patch(task_url(task.id), json=payload, headers=headers)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", next(iter(payload))]
    assert client.get(task_url(task.id), headers=headers).json()["title"] == "Intacta"


@pytest.mark.parametrize("payload", [{}, {"title": "Igual", "priority": "medium"}], ids=["empty", "same"])
def test_patch_without_changes_returns_task_and_writes_nothing(client, ana, create_task, db_session, payload):
    user, headers = ana
    task = create_task(user, "Igual")
    before = client.get(task_url(task.id), headers=headers).json()
    statements = []

    def record(conn, cursor, statement, *args):
        statements.append(statement)

    event.listen(db_session.bind, "before_cursor_execute", record)
    try:
        response = client.patch(task_url(task.id), json=payload, headers=headers)
    finally:
        event.remove(db_session.bind, "before_cursor_execute", record)

    assert response.status_code == 200
    assert response.json() == before  # same updated_at
    assert not [sql for sql in statements if sql.lstrip().upper().startswith("UPDATE")]


def test_patch_task_of_another_user_is_not_found_and_unchanged(client, ana, bia, create_task):
    _, headers = ana
    other_task = create_task(bia[0], "Da Bia")

    response = client.patch(task_url(other_task.id), json={"title": "Invadido"}, headers=headers)

    assert response.status_code == 404
    assert response.json()["detail"] == NOT_FOUND
    assert client.get(task_url(other_task.id), headers=bia[1]).json()["title"] == "Da Bia"


def test_completed_at_lifecycle(client, ana, create_task, freeze_now):
    user, headers = ana
    task = create_task(user)
    url = task_url(task.id)

    freeze_now(T1)
    done = client.patch(url, json={"status": "done"}, headers=headers).json()
    assert parse_dt(done["completed_at"]) == T1

    freeze_now(T1 + timedelta(hours=1))
    still_done = client.patch(url, json={"status": "done", "title": "Renomeada"}, headers=headers).json()
    assert parse_dt(still_done["completed_at"]) == T1

    reopened = client.patch(url, json={"status": "doing"}, headers=headers).json()
    assert reopened["completed_at"] is None

    freeze_now(T1 + timedelta(hours=2))
    done_again = client.patch(url, json={"status": "done"}, headers=headers).json()
    assert parse_dt(done_again["completed_at"]) == T1 + timedelta(hours=2)
    # Persisted, not only in the response.
    assert client.get(url, headers=headers).json() == done_again


def test_completed_at_is_utc(client, ana, create_task, freeze_now):
    user, headers = ana
    task = create_task(user)
    freeze_now(T1)

    body = client.patch(task_url(task.id), json={"status": "done"}, headers=headers).json()

    assert parse_dt(body["completed_at"]).utcoffset() == timedelta(0)


# --- delete ------------------------------------------------------------------------------------


def test_delete_task(client, ana, create_task):
    user, headers = ana
    task = create_task(user)

    response = client.delete(task_url(task.id), headers=headers)

    assert response.status_code == 204
    assert response.content == b""
    assert client.get(task_url(task.id), headers=headers).status_code == 404


def test_delete_task_of_another_user_is_not_found_and_kept(client, ana, bia, create_task, db_session):
    _, headers = ana
    other_task = create_task(bia[0], "Da Bia")

    response = client.delete(task_url(other_task.id), headers=headers)

    assert response.status_code == 404
    assert response.json()["detail"] == NOT_FOUND
    assert db_session.get(Task, other_task.id) is not None


def test_delete_missing_task_is_not_found(client, ana):
    assert client.delete(task_url(uuid.uuid4()), headers=ana[1]).status_code == 404


# --- authentication ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", TASKS_URL),
        ("POST", TASKS_URL),
        ("GET", task_url(uuid.uuid4())),
        ("PATCH", task_url(uuid.uuid4())),
        ("DELETE", task_url(uuid.uuid4())),
    ],
)
def test_task_endpoints_require_authentication(client, method, path):
    response = client.request(method, path, json={"title": "X"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Não autenticado."
    assert response.headers["WWW-Authenticate"] == "Bearer"
