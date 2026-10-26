"""Concurrent writers on the same pet.

- Writers racing a delete of the pet must wait for it and answer 404, never a 500. Without the lock on
  the pet, an event insert that checked the pet just before a concurrent delete committed would fail on
  the composite foreign key (IntegrityError, 500).
- A PATCH of the pet (FOR NO KEY UPDATE) must not hold up event writes (FOR KEY SHARE on the pet).

The first writer is the real service call: its commit is hooked to run the second writer in another
thread first, so the first one's locks are held while the second one runs. Like
tests/test_routines_concurrency.py, these need two real transactions, so they commit to the test
database through `SessionLocal` and delete what they created at the end.
"""

import threading
import uuid
from collections.abc import Callable, Iterator
from datetime import date

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import Pet, PetEvent, User
from app.schemas.pet import PetEventCreate, PetEventUpdate, PetUpdate
from app.services import pet as pet_service
from tests.fakes import FakeStorage
from tests.helpers import make_settings

BLOCKED_FOR = 0.3  # seconds the first writer holds its locks while the second one should wait
NOT_BLOCKED_WITHIN = 5  # seconds the second writer gets to finish while the first one holds its locks
SETTINGS = make_settings()
EVENT = PetEventCreate(type="vet", occurred_on=date(2026, 10, 1))


@pytest.fixture
def committed_pet() -> Iterator[tuple[uuid.UUID, uuid.UUID, uuid.UUID]]:
    """(user_id, pet_id, event_id): a committed pet with one event."""
    with SessionLocal() as db:
        user = User(
            email=f"race-{uuid.uuid4().hex}@example.test", name="Race", password_hash=hash_password("x", 4)
        )
        db.add(user)
        db.flush()
        pet = Pet(user_id=user.id, name="Mel", species="Cachorro")
        db.add(pet)
        db.flush()
        event = PetEvent(user_id=user.id, pet_id=pet.id, type="vaccine", occurred_on=date(2026, 9, 1))
        db.add(event)
        db.commit()
        ids = (user.id, pet.id, event.id)
    yield ids
    with SessionLocal() as db:
        db.execute(delete(User).where(User.id == ids[0]))  # cascades to pets and events
        db.commit()


def run_before_commit(
    first: Callable[[Session], object], second: Callable[[Session], object], wait: float
) -> dict:
    """Run `first` (a service call) and, right before its commit, `second` in another thread.

    `outcome["blocked"]` tells whether `second` was still running after `wait` seconds, i.e. waiting for
    a lock `first` held. `first` commits afterwards in any case, so a blocked `second` finishes too.
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


def count_events(pet_id: uuid.UUID) -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(PetEvent).where(PetEvent.pet_id == pet_id))


@pytest.mark.parametrize(
    "write",
    [
        lambda db, user_id, pet_id, event_id: pet_service.create_event(db, SETTINGS, user_id, pet_id, EVENT),
        lambda db, user_id, pet_id, event_id: pet_service.update_event(
            db, SETTINGS, user_id, pet_id, event_id, PetEventUpdate(description="Reforço")
        ),
        lambda db, user_id, pet_id, event_id: pet_service.delete_event(
            db, FakeStorage(), user_id, pet_id, event_id
        ),
        lambda db, user_id, pet_id, event_id: pet_service.update_pet(
            db, SETTINGS, user_id, pet_id, PetUpdate(name="Mel II")
        ),
    ],
    ids=["create_event", "update_event", "delete_event", "update_pet"],
)
def test_write_waits_for_concurrent_pet_delete_and_is_not_found(committed_pet, write):
    user_id, pet_id, event_id = committed_pet

    outcome = run_before_commit(
        lambda db: pet_service.delete_pet(db, FakeStorage(), user_id, pet_id),
        lambda db: write(db, user_id, pet_id, event_id),
        BLOCKED_FOR,
    )

    assert outcome["blocked"], "the write should wait for the delete holding the lock"
    assert isinstance(outcome.get("error"), pet_service.PetNotFound), repr(outcome)
    assert count_events(pet_id) == 0


def test_pet_patch_does_not_block_event_writes(committed_pet):
    user_id, pet_id, _ = committed_pet

    outcome = run_before_commit(
        lambda db: pet_service.update_pet(db, SETTINGS, user_id, pet_id, PetUpdate(name="Mel II")),
        lambda db: pet_service.create_event(db, SETTINGS, user_id, pet_id, EVENT),
        NOT_BLOCKED_WITHIN,
    )

    assert not outcome["blocked"], "creating an event should not wait for a PATCH of the pet"
    assert "error" not in outcome, repr(outcome)
    assert count_events(pet_id) == 2
    with SessionLocal() as db:
        assert db.get(Pet, pet_id).name == "Mel II"
