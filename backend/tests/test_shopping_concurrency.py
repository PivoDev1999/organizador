"""Two phones using the shopping list (and the pantry) at once.

Like tests/test_pantry_concurrency.py, these need real transactions, so they commit to the test
database through `SessionLocal` and delete what they created at the end. Every operation under test
runs in its own thread and session.
"""

import threading
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import PantryItem, ShoppingItem, User
from app.repositories import pantry as pantry_repo
from app.repositories import shopping as shopping_repo
from app.schemas.shopping import ShoppingItemUpdate
from app.services import shopping as shopping_service
from app.services.shopping import PurchaseResult
from tests.helpers import make_settings

BLOCKED_FOR = 0.3  # seconds a lock is held (or a check delayed) while the other side runs
JOIN_TIMEOUT = 10

Call = Callable[[Session], object]


@dataclass(frozen=True)
class Committed:
    user_id: uuid.UUID
    pantry_item_id: uuid.UUID
    shopping_item_id: uuid.UUID


@pytest.fixture
def committed() -> Iterator[Committed]:
    """A user with a low-stock pantry item P (2 of a minimum of 5 L) and a pending item S (3 L) linked."""
    with SessionLocal() as db:
        user = User(
            email=f"race-{uuid.uuid4().hex}@example.test", name="Race", password_hash=hash_password("x", 4)
        )
        db.add(user)
        db.flush()
        pantry_item = PantryItem(
            user_id=user.id,
            name="Leite",
            category="Laticínios",
            unit="L",
            quantity=Decimal(2),
            min_quantity=Decimal(5),
        )
        db.add(pantry_item)
        db.flush()
        item = ShoppingItem(
            user_id=user.id,
            name="Leite",
            category="Laticínios",
            unit="L",
            quantity=Decimal(3),
            pantry_item_id=pantry_item.id,
        )
        db.add(item)
        db.commit()
        ids = Committed(user.id, pantry_item.id, item.id)
    yield ids
    with SessionLocal() as db:
        db.execute(delete(User).where(User.id == ids.user_id))  # cascades to every item
        db.commit()


def _start(calls: tuple[Call, ...], outcomes: list) -> list[threading.Thread]:
    def worker(index: int, call: Call) -> None:
        with SessionLocal() as db:
            try:
                outcomes[index] = call(db)
            except Exception as exc:  # noqa: BLE001 - the test inspects whatever was raised
                outcomes[index] = exc

    threads = [threading.Thread(target=worker, args=pair) for pair in enumerate(calls)]
    for thread in threads:
        thread.start()
    return threads


def _join(threads: list[threading.Thread]) -> None:
    for thread in threads:
        thread.join(JOIN_TIMEOUT)
    assert not any(thread.is_alive() for thread in threads), "a call never finished"


def run_at_once(*calls: Call) -> list:
    """Run each call in its own thread and transaction, all started together. Returns results/errors."""
    outcomes: list = [None] * len(calls)
    _join(_start(calls, outcomes))
    return outcomes


def run_while_locked(lock: Call, then: Call | None, *calls: Call) -> tuple[list, bool]:
    """In a holder transaction run `lock`, start `calls` (own threads and sessions), wait, run `then`
    and commit. Returns the calls' outcomes and whether all of them were still waiting for the holder."""
    outcomes: list = [None] * len(calls)
    with SessionLocal() as db:
        lock(db)
        threads = _start(calls, outcomes)
        time.sleep(BLOCKED_FOR)
        waited = all(thread.is_alive() for thread in threads)
        if then is not None:
            then(db)
        db.commit()
    _join(threads)
    return outcomes, waited


def delayed(call: Call, seconds: float) -> Call:
    def _call(db: Session) -> object:
        time.sleep(seconds)
        return call(db)

    return _call


def lock_pantry_item(user_id: uuid.UUID, pantry_item_id: uuid.UUID) -> Call:
    return lambda db: pantry_repo.get_for_user(db, user_id, pantry_item_id, for_update=True)


def delete_pantry_item(user_id: uuid.UUID, pantry_item_id: uuid.UUID) -> Call:
    return lambda db: pantry_repo.delete(db, pantry_repo.get_for_user(db, user_id, pantry_item_id))


def slow_pending_check(monkeypatch) -> None:
    """Widen the window between "is there a pending item for P?" and the write that follows."""
    check = shopping_repo.pending_pantry_item_ids

    def _slow(*args):
        found = check(*args)
        time.sleep(BLOCKED_FOR)
        return found

    monkeypatch.setattr(shopping_repo, "pending_pantry_item_ids", _slow)


def stored_item(item_id: uuid.UUID) -> ShoppingItem:
    with SessionLocal() as db:
        return db.scalar(select(ShoppingItem).where(ShoppingItem.id == item_id))


def stored_quantity(pantry_item_id: uuid.UUID) -> Decimal | None:
    with SessionLocal() as db:
        return db.scalar(select(PantryItem.quantity).where(PantryItem.id == pantry_item_id))


def pending_count(user_id: uuid.UUID) -> int:
    with SessionLocal() as db:
        return db.scalar(
            select(func.count())
            .select_from(ShoppingItem)
            .where(ShoppingItem.user_id == user_id, ~ShoppingItem.is_purchased)
        )


def add_pantry_item(user_id: uuid.UUID, name: str = "Leite B") -> uuid.UUID:
    with SessionLocal() as db:
        item = PantryItem(user_id=user_id, name=name, category="Laticínios", unit="L", quantity=Decimal(1))
        db.add(item)
        db.commit()
        return item.id


# --- from-pantry -------------------------------------------------------------------------------


def test_concurrent_from_pantry_calls_do_not_duplicate_items(committed, monkeypatch):
    user_id = committed.user_id
    settings = make_settings()
    with SessionLocal() as db:  # free P: its only pending item is now purchased
        shopping_service.purchase(db, user_id, committed.shopping_item_id)  # 2 + 3 = 5 L: still low
    slow_pending_check(monkeypatch)  # without the lock, both calls would see nothing listed

    def from_pantry(db: Session) -> list:
        return shopping_service.create_from_pantry(db, settings, user_id)

    outcomes = run_at_once(from_pantry, from_pantry)

    assert pending_count(user_id) == 1, "the pantry item was added twice"
    assert sorted(len(outcome) for outcome in outcomes) == [0, 1], repr(outcomes)


def test_unpurchase_during_from_pantry_keeps_at_most_one_pending_item(committed, monkeypatch):
    user_id, item_id = committed.user_id, committed.shopping_item_id
    settings = make_settings()
    with SessionLocal() as db:
        shopping_service.purchase(db, user_id, item_id)
    slow_pending_check(monkeypatch)

    outcomes = run_at_once(
        lambda db: shopping_service.create_from_pantry(db, settings, user_id),
        # Starts while from-pantry holds P and is between its check and its insert.
        delayed(lambda db: shopping_service.unpurchase(db, user_id, item_id), BLOCKED_FOR / 3),
    )

    assert pending_count(user_id) == 1, "two pending items for the same pantry item"
    assert len(outcomes[0]) == 1, repr(outcomes)
    assert isinstance(outcomes[1], shopping_service.PendingItemExists), repr(outcomes)
    assert stored_item(item_id).is_purchased


def test_concurrent_unpurchases_of_the_same_pantry_item_keep_at_most_one_pending(committed, monkeypatch):
    user_id = committed.user_id
    with SessionLocal() as db:
        other = ShoppingItem(
            user_id=user_id,
            name="Leite",
            category="Laticínios",
            unit="L",
            quantity=Decimal(1),
            pantry_item_id=committed.pantry_item_id,
        )
        db.add(other)
        db.commit()
        other_id = other.id
    for item_id in (committed.shopping_item_id, other_id):
        with SessionLocal() as db:
            shopping_service.purchase(db, user_id, item_id)
    slow_pending_check(monkeypatch)

    outcomes = run_at_once(
        lambda db: shopping_service.unpurchase(db, user_id, committed.shopping_item_id),
        lambda db: shopping_service.unpurchase(db, user_id, other_id),
    )

    assert pending_count(user_id) == 1, "two pending items for the same pantry item"
    assert sum(isinstance(outcome, shopping_service.PendingItemExists) for outcome in outcomes) == 1, repr(
        outcomes
    )


# --- purchase ----------------------------------------------------------------------------------


def test_concurrent_purchases_of_the_same_item_let_one_through_and_restock_once(committed):
    user_id, item_id = committed.user_id, committed.shopping_item_id

    def buy(db: Session) -> PurchaseResult:
        return shopping_service.purchase(db, user_id, item_id)

    # The holder only blocks P, so both purchases queue up and then race each other.
    outcomes, waited = run_while_locked(lock_pantry_item(user_id, committed.pantry_item_id), None, buy, buy)

    assert stored_quantity(committed.pantry_item_id) == Decimal("5.000"), "restocked more than once"
    assert sorted(type(outcome).__name__ for outcome in outcomes) == ["AlreadyPurchased", "PurchaseResult"], (
        repr(outcomes)
    )
    assert waited, "both purchases should wait for the lock on the pantry item"


def test_purchase_during_pantry_item_delete_completes_without_the_link(committed):
    user_id, item_id, pantry_item_id = committed.user_id, committed.shopping_item_id, committed.pantry_item_id

    outcomes, waited = run_while_locked(
        lock_pantry_item(user_id, pantry_item_id),
        delete_pantry_item(user_id, pantry_item_id),  # locks P, then S through ON DELETE SET NULL
        lambda db: shopping_service.purchase(db, user_id, item_id),
    )

    (outcome,) = outcomes
    assert isinstance(outcome, PurchaseResult), repr(outcome)
    assert (outcome.pantry_restocked, outcome.item.pantry_item_id) == (False, None)
    stored = stored_item(item_id)
    assert (stored.is_purchased, stored.pantry_item_id) == (True, None)
    assert stored_quantity(pantry_item_id) is None  # deleted
    assert waited


def test_purchase_follows_a_link_changed_while_it_waited(committed):
    user_id, item_id = committed.user_id, committed.shopping_item_id
    other_pantry_item_id = add_pantry_item(user_id)

    def relink(db: Session) -> None:
        shopping_repo.get_for_user(db, user_id, item_id).pantry_item_id = other_pantry_item_id
        db.flush()

    outcomes, waited = run_while_locked(
        lambda db: shopping_repo.get_for_user(db, user_id, item_id, for_update=True),
        relink,
        lambda db: shopping_service.purchase(db, user_id, item_id),
    )

    (outcome,) = outcomes
    assert isinstance(outcome, PurchaseResult) and outcome.pantry_restocked, repr(outcome)
    assert stored_quantity(other_pantry_item_id) == Decimal("4.000")  # 1 + 3: the new link
    assert stored_quantity(committed.pantry_item_id) == Decimal("2.000")  # the old one is untouched
    assert waited


# --- update ------------------------------------------------------------------------------------


def test_relink_during_delete_of_the_target_pantry_item_is_422_not_500(committed):
    user_id, item_id = committed.user_id, committed.shopping_item_id
    target_id = add_pantry_item(user_id)

    outcomes, waited = run_while_locked(
        lock_pantry_item(user_id, target_id),
        delete_pantry_item(user_id, target_id),
        lambda db: shopping_service.update_item(
            db, user_id, item_id, ShoppingItemUpdate(pantry_item_id=target_id)
        ),
    )

    assert isinstance(outcomes[0], shopping_service.PantryItemNotFound), repr(outcomes)
    assert stored_item(item_id).pantry_item_id == committed.pantry_item_id
    assert waited
