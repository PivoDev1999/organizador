"""Concurrent writers on the same routine: marking it done while someone deactivates it or marks it too.

Like tests/test_tasks_concurrency.py, these need two real transactions, so they commit to the test
database through `SessionLocal` and delete what they created at the end.
"""

import threading
import uuid
from collections.abc import Callable, Iterator

import pytest
from sqlalchemy import delete, func, select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import Routine, RoutineLog, User
from app.repositories import routine as routine_repo
from app.schemas.routine import RoutineLogCreate
from app.services import routine as routine_service
from tests.helpers import make_settings

BLOCKED_FOR = 0.3  # seconds the first writer holds the lock while the second one waits


@pytest.fixture
def committed_routine() -> Iterator[tuple[uuid.UUID, uuid.UUID]]:
    with SessionLocal() as db:
        user = User(
            email=f"race-{uuid.uuid4().hex}@example.test", name="Race", password_hash=hash_password("x", 4)
        )
        db.add(user)
        db.flush()
        routine = Routine(user_id=user.id, name="Regar as plantas", frequency="daily")
        db.add(routine)
        db.commit()
        ids = (user.id, routine.id)
    yield ids
    with SessionLocal() as db:
        db.execute(delete(User).where(User.id == ids[0]))  # cascades to routine and logs
        db.commit()


def run_while_locked(user_id: uuid.UUID, routine_id: uuid.UUID, first: Callable, second: Callable) -> dict:
    """Lock the routine in one transaction, start `second` in another thread, then let `first` finish."""
    outcome: dict = {}

    def second_writer() -> None:
        with SessionLocal() as db:
            try:
                outcome["result"] = second(db)
            except Exception as exc:  # noqa: BLE001 - the test inspects whatever was raised
                outcome["error"] = exc

    with SessionLocal() as db:
        routine = routine_repo.get_for_user(db, user_id, routine_id, for_update=True)
        thread = threading.Thread(target=second_writer)
        thread.start()
        thread.join(BLOCKED_FOR)
        outcome["waited"] = thread.is_alive()
        first(db, routine)
        db.commit()
    thread.join(10)
    assert not thread.is_alive(), "second writer never finished"
    return outcome


def log_today(user_id: uuid.UUID, routine_id: uuid.UUID) -> Callable:
    settings = make_settings()
    return lambda db: routine_service.log_done(db, settings, user_id, routine_id, RoutineLogCreate())


def count_logs(routine_id: uuid.UUID) -> int:
    with SessionLocal() as db:
        return db.scalar(
            select(func.count()).select_from(RoutineLog).where(RoutineLog.routine_id == routine_id)
        )


def test_log_waits_for_concurrent_deactivation_and_is_rejected(committed_routine):
    user_id, routine_id = committed_routine

    def deactivate(db, routine):
        routine.is_active = False

    outcome = run_while_locked(user_id, routine_id, deactivate, log_today(user_id, routine_id))

    assert outcome["waited"], "marking as done should wait for the PATCH holding the lock"
    assert isinstance(outcome.get("error"), routine_service.RoutineInactive), repr(outcome)
    assert count_logs(routine_id) == 0


def test_two_concurrent_logs_for_the_same_day_keep_one(committed_routine):
    user_id, routine_id = committed_routine
    settings = make_settings()

    def log_first(db, routine):
        routine_service.log_done(db, settings, user_id, routine_id, RoutineLogCreate())

    outcome = run_while_locked(user_id, routine_id, log_first, log_today(user_id, routine_id))

    assert outcome["waited"]
    assert isinstance(outcome.get("error"), routine_service.RoutineAlreadyDone), repr(outcome)
    assert count_logs(routine_id) == 1
