"""Concurrent writers on the same task (two phones, same household).

These tests need two real transactions, so they commit to the test database through `SessionLocal`
instead of the rolled-back `db_session` fixture, and delete what they created at the end.
"""

import threading
import uuid
from collections.abc import Callable, Iterator

import pytest
from sqlalchemy import delete, inspect, text

from app.core import clock
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import Task, User
from app.repositories import task as task_repo
from app.schemas.task import TaskUpdate
from app.services import task as task_service
from tests.fakes import FakeStorage

BLOCKED_FOR = 0.3  # seconds the first writer holds the lock while the second one waits


@pytest.fixture
def committed_task() -> Iterator[tuple[uuid.UUID, uuid.UUID]]:
    with SessionLocal() as db:
        user = User(
            email=f"race-{uuid.uuid4().hex}@example.test", name="Race", password_hash=hash_password("x", 4)
        )
        db.add(user)
        db.flush()
        task = Task(user_id=user.id, title="Regar as plantas")
        db.add(task)
        db.commit()
        ids = (user.id, task.id)
    yield ids
    with SessionLocal() as db:
        db.execute(delete(User).where(User.id == ids[0]))  # cascades to the task
        db.commit()


def run_while_locked(user_id: uuid.UUID, task_id: uuid.UUID, first: Callable, second: Callable) -> dict:
    """Lock the task in one transaction, start `second` in another thread, then let `first` finish.

    Returns what `second` produced (`result`) or raised (`error`), and whether it really had to wait.
    """
    outcome: dict = {}

    def second_writer() -> None:
        with SessionLocal() as db:
            try:
                outcome["result"] = second(db)
            except Exception as exc:  # noqa: BLE001 - the test inspects whatever was raised
                outcome["error"] = exc

    with SessionLocal() as db:
        task = task_repo.get_for_user(db, user_id, task_id, for_update=True)
        thread = threading.Thread(target=second_writer)
        thread.start()
        thread.join(BLOCKED_FOR)
        outcome["waited"] = thread.is_alive()
        first(db, task)
        db.commit()
    thread.join(10)
    assert not thread.is_alive(), "second writer never finished"
    return outcome


def test_concurrent_status_changes_end_in_a_consistent_task(committed_task):
    user_id, task_id = committed_task

    def mark_done(db, task):
        task.status = "done"
        task.completed_at = clock.now_utc()

    def mark_doing(db):
        task = task_service.update_task(db, user_id, task_id, TaskUpdate(status="doing"))
        return task.status, task.completed_at

    outcome = run_while_locked(user_id, task_id, mark_done, mark_doing)

    assert outcome["waited"], "the second PATCH should wait for the first one's lock"
    assert "error" not in outcome, repr(outcome.get("error"))
    assert outcome["result"] == ("doing", None)
    with SessionLocal() as db:
        stored = db.get(Task, task_id)
        assert (stored.status, stored.completed_at) == ("doing", None)


@pytest.mark.parametrize(
    "second",
    [
        lambda db, user_id, task_id: task_service.update_task(
            db, user_id, task_id, TaskUpdate(title="Outra")
        ),
        lambda db, user_id, task_id: task_service.delete_task(db, FakeStorage(), user_id, task_id),
    ],
    ids=["patch", "delete"],
)
def test_writer_after_concurrent_delete_gets_not_found(committed_task, second):
    user_id, task_id = committed_task

    outcome = run_while_locked(
        user_id,
        task_id,
        lambda db, task: task_repo.delete(db, task),
        lambda db: second(db, user_id, task_id),
    )

    assert outcome["waited"]
    assert isinstance(outcome.get("error"), task_service.TaskNotFound), repr(outcome)


def test_update_leaves_nothing_to_reload_after_commit(committed_task):
    """updated_at comes back with RETURNING, so serializing never re-reads a row deleted meanwhile."""
    user_id, task_id = committed_task

    with SessionLocal() as db:
        task = task_service.update_task(db, user_id, task_id, TaskUpdate(status="doing"))
        assert not inspect(task).expired_attributes
        with SessionLocal() as other:  # someone else deletes it right after our commit
            other.execute(delete(Task).where(Task.id == task_id))
            other.commit()
        assert task.updated_at is not None  # no lazy SELECT, so no ObjectDeletedError


def test_update_without_changes_releases_the_lock(committed_task):
    user_id, task_id = committed_task

    with SessionLocal() as db:
        task_service.update_task(db, user_id, task_id, TaskUpdate(title="Regar as plantas"))
        assert not db.in_transaction()  # committed: the FOR UPDATE lock is gone before the response
        with SessionLocal() as other:
            other.execute(text("SET LOCAL lock_timeout = '1s'"))
            task_service.delete_task(other, FakeStorage(), user_id, task_id)  # would time out if still locked
