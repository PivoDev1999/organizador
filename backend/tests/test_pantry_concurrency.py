"""Two phones changing the stock of the same item at once.

Like tests/test_routines_concurrency.py, these need two real transactions, so they commit to the test
database through `SessionLocal` and delete what they created at the end.
"""

import threading
import uuid
from collections.abc import Callable, Iterator
from decimal import Decimal

import pytest
from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import PantryItem, User
from app.repositories import pantry as pantry_repo
from app.schemas.pantry import StockChange
from app.services import pantry as pantry_service
from tests.helpers import make_settings

BLOCKED_FOR = 0.3  # seconds the first writer holds the lock while the second one waits


@pytest.fixture
def committed_item() -> Iterator[tuple[uuid.UUID, uuid.UUID]]:
    with SessionLocal() as db:
        user = User(
            email=f"race-{uuid.uuid4().hex}@example.test", name="Race", password_hash=hash_password("x", 4)
        )
        db.add(user)
        db.flush()
        item = PantryItem(user_id=user.id, name="Leite", category="Laticínios", unit="L", quantity=Decimal(5))
        db.add(item)
        db.commit()
        ids = (user.id, item.id)
    yield ids
    with SessionLocal() as db:
        db.execute(delete(User).where(User.id == ids[0]))  # cascades to the item
        db.commit()


def consume(user_id: uuid.UUID, item_id: uuid.UUID, amount: str) -> Callable:
    settings = make_settings()
    return lambda db: pantry_service.consume(db, settings, user_id, item_id, StockChange(amount=amount))


def run_while_locked(user_id: uuid.UUID, item_id: uuid.UUID, first: Callable, second: Callable) -> dict:
    """Lock the item in one transaction, start `second` in another thread, then let `first` finish."""
    outcome: dict = {}

    def second_writer() -> None:
        with SessionLocal() as db:
            try:
                outcome["result"] = second(db)
            except Exception as exc:  # noqa: BLE001 - the test inspects whatever was raised
                outcome["error"] = exc

    with SessionLocal() as db:
        pantry_repo.get_for_user(db, user_id, item_id, for_update=True)
        thread = threading.Thread(target=second_writer)
        thread.start()
        thread.join(BLOCKED_FOR)
        outcome["waited"] = thread.is_alive()
        first(db)
        db.commit()
    thread.join(10)
    assert not thread.is_alive(), "second writer never finished"
    return outcome


def stored_quantity(item_id: uuid.UUID) -> Decimal:
    with SessionLocal() as db:
        return db.scalar(select(PantryItem.quantity).where(PantryItem.id == item_id))


def test_two_concurrent_consumes_are_both_counted(committed_item):
    user_id, item_id = committed_item

    outcome = run_while_locked(
        user_id, item_id, consume(user_id, item_id, "2"), consume(user_id, item_id, "2")
    )

    assert outcome["waited"], "the second consume should wait for the first one's lock"
    assert "error" not in outcome, repr(outcome)
    assert outcome["result"].item.quantity == Decimal("1.000")
    assert stored_quantity(item_id) == Decimal("1.000")


def test_concurrent_consumes_beyond_the_stock_let_only_one_through(committed_item):
    user_id, item_id = committed_item

    outcome = run_while_locked(
        user_id, item_id, consume(user_id, item_id, "3"), consume(user_id, item_id, "3")
    )

    assert outcome["waited"]
    assert isinstance(outcome.get("error"), pantry_service.InsufficientStock), repr(outcome)
    assert stored_quantity(item_id) == Decimal("2.000")
