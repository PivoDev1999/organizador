"""Concurrent writers on the same event, and an attachment upload racing the delete of its event.

Like tests/test_tasks_concurrency.py and tests/test_files_concurrency.py, these need two real
transactions, so they commit to the test database through `SessionLocal` instead of the rolled-back
`db_session` fixture, and delete what they created at the end.
"""

import io
import threading
import uuid
from collections.abc import Callable, Iterator
from datetime import date

import pytest
from sqlalchemy import delete, func, select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import Event, File, User
from app.repositories import event as event_repo
from app.schemas.event import EventUpdate
from app.schemas.file import FileCreate
from app.services import event as event_service
from app.services import files as files_service
from tests.fakes import FakeStorage
from tests.helpers import PNG, make_settings

BLOCKED_FOR = 0.3  # seconds the first transaction holds its lock while the second one waits
SETTINGS = make_settings()


@pytest.fixture
def committed_event() -> Iterator[tuple[uuid.UUID, uuid.UUID]]:
    """(user_id, event_id), committed."""
    with SessionLocal() as db:
        user = User(
            email=f"race-{uuid.uuid4().hex}@example.test", name="Race", password_hash=hash_password("x", 4)
        )
        db.add(user)
        db.flush()
        event = Event(user_id=user.id, title="Consulta", starts_on=date(2026, 11, 10))
        db.add(event)
        db.commit()
        ids = (user.id, event.id)
    yield ids
    with SessionLocal() as db:
        db.execute(delete(User).where(User.id == ids[0]))  # cascades to events and files
        db.commit()


def run_concurrently(first: Callable, second: Callable) -> dict:
    """Run `first` and, right before its commit, `second` in another thread.

    Returns what `second` produced (`result`) or raised (`error`), and whether it was still blocked
    after BLOCKED_FOR seconds (`blocked`).
    """
    outcome: dict = {}

    def second_writer() -> None:
        with SessionLocal() as db:
            try:
                outcome["result"] = second(db)
            except Exception as exc:  # noqa: BLE001 - the test inspects whatever was raised
                outcome["error"] = exc

    thread = threading.Thread(target=second_writer)
    with SessionLocal() as db:
        real_commit = db.commit

        def commit_after_second() -> None:
            thread.start()
            thread.join(BLOCKED_FOR)
            outcome["blocked"] = thread.is_alive()
            real_commit()

        db.commit = commit_after_second
        first(db)
    thread.join(10)
    assert not thread.is_alive(), "second writer never finished"
    return outcome


def test_patch_after_a_concurrent_delete_gets_not_found(committed_event):
    user_id, event_id = committed_event

    def delete_locked(db) -> None:
        event_repo.delete(db, event_service.get_event(db, user_id, event_id, for_update=True))
        db.commit()

    outcome = run_concurrently(
        delete_locked,
        lambda db: event_service.update_event(db, user_id, event_id, EventUpdate(title="Outra")),
    )

    assert outcome["blocked"], "the PATCH should wait for the delete's lock"
    assert isinstance(outcome.get("error"), event_service.EventNotFound), repr(outcome)


def test_delete_waits_for_the_patch_and_then_removes_the_event(committed_event):
    user_id, event_id = committed_event

    outcome = run_concurrently(
        lambda db: event_service.update_event(db, user_id, event_id, EventUpdate(title="Retorno")),
        lambda db: event_service.delete_event(db, FakeStorage(), user_id, event_id),
    )

    assert outcome["blocked"], "the delete should wait for the PATCH's lock"
    assert "error" not in outcome, repr(outcome)
    with SessionLocal() as db:
        assert db.get(Event, event_id) is None


def test_delete_waits_for_an_upload_and_then_removes_its_attachment(committed_event):
    user_id, event_id = committed_event
    storage = FakeStorage()
    data = FileCreate(entity_type="event", entity_id=event_id)

    outcome = run_concurrently(
        lambda db: files_service.upload_file(
            db, storage, SETTINGS, user_id, data, io.BytesIO(PNG), "a.png", None
        ),
        lambda db: event_service.delete_event(db, storage, user_id, event_id),
    )

    assert outcome["blocked"], "the delete did not wait for the upload's KEY SHARE lock"
    assert "error" not in outcome, repr(outcome)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(File).where(File.user_id == user_id)) == 0
    assert storage.objects == {} and len(storage.deleted) == 1
