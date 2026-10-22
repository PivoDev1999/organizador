"""Unit tests of app.services.task, called directly with a database session (no HTTP)."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from app.core import clock
from app.models import Task
from app.schemas.task import TaskCreate, TaskQuery, TaskUpdate
from app.services import task as task_service
from tests.helpers import make_settings

T0 = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
T1 = datetime(2026, 10, 19, 15, 0, tzinfo=UTC)


@pytest.fixture
def freeze_now(monkeypatch):
    def _freeze(moment: datetime) -> None:
        monkeypatch.setattr(clock, "now_utc", lambda: moment)

    return _freeze


@pytest.fixture
def ana(create_user):
    return create_user("ana@example.test")


@pytest.fixture
def bia(create_user):
    return create_user("bia@example.test")


@pytest.fixture
def task_in(ana, create_task):
    """A task of Ana in a given status; done tasks were completed at T0."""

    def _make(status: str = "todo", **fields) -> Task:
        if status == "done":
            fields.setdefault("completed_at", T0)
        return create_task(ana, "Tarefa", status=status, **fields)

    return _make


# --- create ------------------------------------------------------------------------------------


@pytest.mark.parametrize(("status", "completed"), [("todo", False), ("doing", False), ("done", True)])
def test_create_sets_completed_at_only_for_done(db_session, ana, freeze_now, status, completed):
    freeze_now(T1)

    task = task_service.create_task(db_session, ana.id, TaskCreate(title="X", status=status))

    assert task.completed_at == (T1 if completed else None)
    db_session.expire_all()
    assert db_session.get(Task, task.id).completed_at == (T1 if completed else None)


def test_create_assigns_owner_and_server_fields(db_session, ana):
    task = task_service.create_task(db_session, ana.id, TaskCreate(title="X"))

    assert task.user_id == ana.id
    assert isinstance(task.id, uuid.UUID)
    assert task.created_at is not None
    assert task.updated_at is not None


# --- completed_at transitions ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        ("todo", "done", T1),
        ("doing", "done", T1),
        ("done", "todo", None),
        ("done", "doing", None),
        ("done", "done", T0),
        ("todo", "doing", None),
        ("doing", "todo", None),
        ("todo", "todo", None),
    ],
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_status_transition_sets_completed_at(db_session, ana, task_in, freeze_now, before, after, expected):
    task = task_in(before)
    freeze_now(T1)

    updated = task_service.update_task(db_session, ana.id, task.id, TaskUpdate(status=after))

    assert updated.status == after
    assert updated.completed_at == expected
    db_session.expire_all()
    assert db_session.get(Task, task.id).completed_at == expected


@pytest.mark.parametrize(
    "data",
    [
        {"title": "Renomeada"},
        {"priority": "high"},
        {"description": "Nova"},
        {"due_date": date(2026, 12, 1)},
        {"title": "Renomeada", "status": "done"},
    ],
    ids=["title", "priority", "description", "due-date", "title-and-same-status"],
)
def test_editing_done_task_keeps_completed_at(db_session, ana, task_in, freeze_now, data):
    task = task_in("done")
    freeze_now(T1)

    updated = task_service.update_task(db_session, ana.id, task.id, TaskUpdate(**data))

    assert updated.completed_at == T0
    assert updated.status == "done"
    for field, value in data.items():
        assert getattr(updated, field) == value


def test_editing_open_task_without_status_keeps_completed_at_null(db_session, ana, task_in, freeze_now):
    task = task_in("doing")
    freeze_now(T1)

    updated = task_service.update_task(db_session, ana.id, task.id, TaskUpdate(title="Outra"))

    assert updated.completed_at is None


def test_redone_task_gets_new_completed_at(db_session, ana, task_in, freeze_now):
    task = task_in("done")

    freeze_now(T1)
    task_service.update_task(db_session, ana.id, task.id, TaskUpdate(status="todo"))
    freeze_now(T1 + timedelta(days=1))
    updated = task_service.update_task(db_session, ana.id, task.id, TaskUpdate(status="done"))

    assert updated.completed_at == T1 + timedelta(days=1)


def test_update_without_changes_does_not_call_clock(db_session, ana, task_in, monkeypatch):
    task = task_in("done")

    def _boom():
        raise AssertionError("clock must not be read when nothing changes")

    monkeypatch.setattr(clock, "now_utc", _boom)

    updated = task_service.update_task(db_session, ana.id, task.id, TaskUpdate(status="done", title="Tarefa"))

    assert updated.completed_at == T0


def test_update_null_clears_nullable_fields(db_session, ana, task_in):
    task = task_in(description="Desc", due_date=date(2026, 5, 1))

    updated = task_service.update_task(
        db_session, ana.id, task.id, TaskUpdate(description=None, due_date=None)
    )

    assert (updated.description, updated.due_date) == (None, None)


def test_update_ignores_fields_not_sent(db_session, ana, task_in):
    task = task_in(description="Desc", priority="high", due_date=date(2026, 5, 1))

    updated = task_service.update_task(db_session, ana.id, task.id, TaskUpdate(title="Nova"))

    assert (updated.description, updated.priority, updated.due_date) == ("Desc", "high", date(2026, 5, 1))


# --- not found and isolation -------------------------------------------------------------------


@pytest.mark.parametrize("operation", ["get", "update", "delete"])
def test_other_users_task_raises_not_found(db_session, ana, bia, create_task, operation):
    task = create_task(bia, "Da Bia")
    call = {
        "get": lambda: task_service.get_task(db_session, ana.id, task.id),
        "update": lambda: task_service.update_task(db_session, ana.id, task.id, TaskUpdate(title="Invadida")),
        "delete": lambda: task_service.delete_task(db_session, ana.id, task.id),
    }[operation]

    with pytest.raises(task_service.TaskNotFound) as exc_info:
        call()

    assert exc_info.value.detail == "Tarefa não encontrada."
    db_session.expire_all()
    assert db_session.get(Task, task.id).title == "Da Bia"


@pytest.mark.parametrize("operation", ["get", "update", "delete"])
def test_missing_task_raises_not_found(db_session, ana, operation):
    missing = uuid.uuid4()
    call = {
        "get": lambda: task_service.get_task(db_session, ana.id, missing),
        "update": lambda: task_service.update_task(db_session, ana.id, missing, TaskUpdate()),
        "delete": lambda: task_service.delete_task(db_session, ana.id, missing),
    }[operation]

    with pytest.raises(task_service.TaskNotFound):
        call()


def test_delete_removes_only_the_given_task(db_session, ana, create_task):
    kept = create_task(ana, "Fica")
    gone = create_task(ana, "Sai")

    task_service.delete_task(db_session, ana.id, gone.id)

    db_session.expire_all()
    assert db_session.get(Task, gone.id) is None
    assert db_session.get(Task, kept.id) is not None


def test_list_only_returns_the_users_tasks(db_session, ana, bia, create_task):
    mine = create_task(ana, "Minha")
    create_task(bia, "Minha")  # same title: the filter is by owner, not by content

    items, total = task_service.list_tasks(db_session, make_settings(), ana.id, TaskQuery())

    assert [task.id for task in items] == [mine.id]
    assert total == 1


# --- overdue and the app timezone --------------------------------------------------------------


@pytest.mark.parametrize(
    ("timezone", "overdue"),
    [
        # 2026-05-10 23:30 UTC is still May 10 in São Paulo but May 11 in Tokyo and Kiritimati.
        ("America/Sao_Paulo", False),
        ("UTC", False),
        ("Asia/Tokyo", True),
        ("Pacific/Kiritimati", True),
        ("Pacific/Pago_Pago", False),
    ],
)
def test_list_overdue_uses_settings_timezone(db_session, ana, create_task, freeze_now, timezone, overdue):
    freeze_now(datetime(2026, 5, 10, 23, 30, tzinfo=UTC))
    task = create_task(ana, "Vence dia 10", due_date=date(2026, 5, 10))

    items, total = task_service.list_tasks(
        db_session, make_settings(app_timezone=timezone), ana.id, TaskQuery(overdue=True)
    )

    assert [t.id for t in items] == ([task.id] if overdue else [])
    assert total == (1 if overdue else 0)


def test_list_without_overdue_does_not_read_clock(db_session, ana, monkeypatch):
    def _boom():
        raise AssertionError("clock must not be read without overdue=true")

    monkeypatch.setattr(clock, "now_utc", _boom)

    assert task_service.list_tasks(db_session, make_settings(), ana.id, TaskQuery()) == ([], 0)
