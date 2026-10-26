"""Upload of an attachment racing a delete of its record.

`files` has no FK to the record, so only locks keep an attachment from outliving it: the upload holds
FOR KEY SHARE on the record (`exists_for_user`) from its last check to its commit, and every delete
locks the record FOR UPDATE and removes the attachments after it.

Like tests/test_pets_concurrency.py, these need two real transactions, so they commit to the test
database through `SessionLocal` and delete what they created at the end.
"""

import io
import threading
import uuid
from collections.abc import Callable, Iterator

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import File, Task, User
from app.schemas.file import FileCreate
from app.services import files as files_service
from app.services import task as task_service
from tests.fakes import FakeStorage
from tests.helpers import PNG, make_settings

BLOCKED_FOR = 0.3  # seconds the upload holds its lock while the delete should wait
SETTINGS = make_settings()


@pytest.fixture
def committed_task() -> Iterator[tuple[uuid.UUID, uuid.UUID]]:
    """(user_id, task_id), committed."""
    with SessionLocal() as db:
        user = User(
            email=f"race-{uuid.uuid4().hex}@example.test", name="Race", password_hash=hash_password("x", 4)
        )
        db.add(user)
        db.flush()
        task = Task(user_id=user.id, title="Nota fiscal")
        db.add(task)
        db.commit()
        ids = (user.id, task.id)
    yield ids
    with SessionLocal() as db:
        db.execute(delete(User).where(User.id == ids[0]))  # cascades to tasks and files
        db.commit()


def run_before_commit(
    first: Callable[[Session], object], second: Callable[[Session], object], wait: float
) -> dict:
    """Run `first` and, right before its commit, `second` in another thread (see test_pets_concurrency).

    `outcome["blocked"]` tells whether `second` was still running after `wait` seconds.
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
            thread.join(wait)
            outcome["blocked"] = thread.is_alive()
            real_commit()

        db.commit = commit_after_second
        first(db)
    thread.join(10)
    assert not thread.is_alive(), "second writer never finished"
    return outcome


def upload(db: Session, storage: FakeStorage, user_id: uuid.UUID, task_id: uuid.UUID) -> File:
    data = FileCreate(entity_type="task", entity_id=task_id)
    return files_service.upload_file(db, storage, SETTINGS, user_id, data, io.BytesIO(PNG), "a.png", None)


def count_files(user_id: uuid.UUID) -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(File).where(File.user_id == user_id))


def test_delete_waits_for_the_upload_and_then_removes_its_attachment(committed_task):
    user_id, task_id = committed_task
    storage = FakeStorage()

    outcome = run_before_commit(
        lambda db: upload(db, storage, user_id, task_id),
        lambda db: task_service.delete_task(db, storage, user_id, task_id),
        BLOCKED_FOR,
    )

    assert outcome["blocked"], "the delete did not wait for the upload's KEY SHARE lock"
    assert "error" not in outcome, repr(outcome)
    assert count_files(user_id) == 0
    assert storage.objects == {} and len(storage.deleted) == 1


def test_upload_after_the_delete_committed_is_422_and_removes_its_object(committed_task):
    user_id, task_id = committed_task

    class DeleteDuringPut(FakeStorage):
        """The record is deleted (and committed) while its file is being stored."""

        def put(self, key, stream, content_type):
            super().put(key, stream, content_type)
            with SessionLocal() as other:
                task_service.delete_task(other, FakeStorage(), user_id, task_id)

    storage = DeleteDuringPut()

    with SessionLocal() as db, pytest.raises(files_service.EntityNotFound):
        upload(db, storage, user_id, task_id)

    assert count_files(user_id) == 0
    assert storage.objects == {} and len(storage.deleted) == 1
