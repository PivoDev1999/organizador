"""Two phones using the finances at once.

- Budgets: "Mercado" and "mercado" are the same category, but the UNIQUE constraint is case-sensitive;
  the per-(user, month) advisory lock must let only one of two concurrent creates through.
- Lock order pet -> transaction: a PATCH that sets `pet_id` racing a delete of that pet (which locks the
  pet and then SET NULLs its transactions) must never deadlock nor fail with a 500.
- Paying twice at once: one payment, one 409.
- Every write on a transaction racing a delete of its pet (in both orders) ends without deadlock or 500.
- A budget deleted by another device right after a create/update commits must not turn the answer
  into a 500.

Like tests/test_shopping_concurrency.py, these need real transactions, so they commit to the test
database through `SessionLocal` and delete what they created at the end. Every operation under test
runs in its own thread and session.
"""

import threading
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import Budget, Pet, Transaction, User
from app.repositories import budget as budget_repo
from app.repositories import transaction as transaction_repo
from app.schemas.finance import BudgetCreate, BudgetUpdate, TransactionCreate, TransactionUpdate
from app.services import budget as budget_service
from app.services import pet as pet_service
from app.services import transaction as transaction_service
from app.services.transaction import TransactionView
from tests.fakes import FakeStorage
from tests.helpers import make_settings

BLOCKED_FOR = 0.3  # seconds a lock is held (or a step delayed) while the other side runs
JOIN_TIMEOUT = 10
SETTINGS = make_settings()

Call = Callable[[Session], object]


@dataclass(frozen=True)
class Committed:
    user_id: uuid.UUID
    mel_id: uuid.UUID
    bidu_id: uuid.UUID
    transaction_id: uuid.UUID  # pending expense linked to Mel


@pytest.fixture
def committed() -> Iterator[Committed]:
    with SessionLocal() as db:
        user = User(
            email=f"race-{uuid.uuid4().hex}@example.test", name="Race", password_hash=hash_password("x", 4)
        )
        db.add(user)
        db.flush()
        mel = Pet(user_id=user.id, name="Mel", species="Cachorro")
        bidu = Pet(user_id=user.id, name="Bidu", species="Cachorro")
        db.add_all([mel, bidu])
        db.flush()
        transaction = Transaction(
            user_id=user.id,
            type="expense",
            amount=Decimal("189.90"),
            category="Pets",
            due_date=date(2026, 10, 21),
            pet_id=mel.id,
        )
        db.add(transaction)
        db.commit()
        ids = Committed(user.id, mel.id, bidu.id, transaction.id)
    yield ids
    with SessionLocal() as db:
        db.execute(delete(User).where(User.id == ids.user_id))  # cascades to everything
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


def run_while_locked(lock: Call, *calls: Call) -> tuple[list, bool]:
    """In a holder transaction run `lock`, start `calls`, wait, commit. Returns the calls' outcomes and
    whether all of them were still waiting for the holder."""
    outcomes: list = [None] * len(calls)
    with SessionLocal() as db:
        lock(db)
        threads = _start(calls, outcomes)
        time.sleep(BLOCKED_FOR)
        waited = all(thread.is_alive() for thread in threads)
        db.commit()
    _join(threads)
    return outcomes, waited


def delayed(call: Call, seconds: float) -> Call:
    def _call(db: Session) -> object:
        time.sleep(seconds)
        return call(db)

    return _call


def stored_transaction(transaction_id: uuid.UUID) -> Transaction:
    with SessionLocal() as db:
        return db.scalar(select(Transaction).where(Transaction.id == transaction_id))


# --- budgets -------------------------------------------------------------------------------------


def test_concurrent_creates_differing_only_in_case_let_one_through(committed, monkeypatch):
    user_id = committed.user_id
    check = budget_repo.category_exists

    def slow_check(*args):  # widen the window between "is there one?" and the insert
        found = check(*args)
        time.sleep(BLOCKED_FOR)
        return found

    monkeypatch.setattr(budget_repo, "category_exists", slow_check)

    def create(category: str) -> Call:
        data = BudgetCreate(category=category, month="2026-10", amount="500")
        return lambda db: budget_service.create_budget(db, user_id, data)

    outcomes = run_at_once(create("Mercado"), create("mercado"))

    assert sorted(type(outcome).__name__ for outcome in outcomes) == ["BudgetExists", "BudgetView"], repr(
        outcomes
    )
    with SessionLocal() as db:
        count = db.scalar(select(func.count()).select_from(Budget).where(Budget.user_id == user_id))
    assert count == 1


# --- pet link -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("patch", "deleted"),
    [
        # A form that sends every field: the same pet again, plus the real change.
        (lambda ids: {"pet_id": ids.mel_id, "amount": "99.00"}, "mel"),
        # Switching to a pet that is being deleted.
        (lambda ids: {"pet_id": ids.bidu_id}, "bidu"),
    ],
    ids=["resend-same-pet", "switch-to-deleted-pet"],
)
def test_patch_setting_pet_id_during_delete_of_that_pet_neither_deadlocks_nor_fails(
    committed, monkeypatch, patch, deleted
):
    ids = committed
    pet_id = getattr(ids, f"{deleted}_id")
    get_for_user = transaction_repo.get_for_user

    def slow_lock(*args, **kwargs):  # hold the transaction lock a while before going on
        found = get_for_user(*args, **kwargs)
        if kwargs.get("for_update"):
            time.sleep(BLOCKED_FOR)
        return found

    monkeypatch.setattr(transaction_repo, "get_for_user", slow_lock)
    data = TransactionUpdate(**patch(ids))

    outcomes = run_at_once(
        lambda db: transaction_service.update_transaction(
            db, SETTINGS, ids.user_id, ids.transaction_id, data
        ),
        # Starts while the PATCH holds its locks.
        delayed(lambda db: pet_service.delete_pet(db, FakeStorage(), ids.user_id, pet_id), BLOCKED_FOR / 3),
    )

    assert isinstance(outcomes[0], TransactionView), repr(outcomes)
    assert outcomes[1] is None, repr(outcomes)
    stored = stored_transaction(ids.transaction_id)
    # The PATCH committed first; the delete then cleared the link of its pet.
    assert stored.pet_id is None
    assert stored.amount == Decimal(patch(ids).get("amount", "189.90"))


# --- pay -----------------------------------------------------------------------------------------


def test_concurrent_payments_let_one_through(committed):
    ids = committed

    def pay(db: Session) -> TransactionView:
        return transaction_service.pay(db, SETTINGS, ids.user_id, ids.transaction_id, None)

    # The holder locks the row, so both payments queue up and then race each other.
    outcomes, waited = run_while_locked(
        lambda db: transaction_repo.get_for_user(db, ids.user_id, ids.transaction_id, for_update=True),
        pay,
        pay,
    )

    assert sorted(type(outcome).__name__ for outcome in outcomes) == ["AlreadyPaid", "TransactionView"], repr(
        outcomes
    )
    assert waited
    assert stored_transaction(ids.transaction_id).paid_at is not None


# --- budgets: answer built before the commit ------------------------------------------------------


@pytest.mark.parametrize("write", ["create", "update"])
def test_budget_deleted_right_after_the_commit_still_gets_an_answer(committed, write):
    """The view (with `spent`) is built before the commit: another device deleting the budget right
    after it must not make the answer fail (it used to re-read the row after commit: ValueError, 500)."""
    user_id = committed.user_id
    with SessionLocal() as db:
        budget_id = None
        if write == "update":
            budget_id = budget_service.create_budget(
                db, user_id, BudgetCreate(category="Pets", month="2026-10", amount="300")
            ).budget.id
        real_commit = db.commit

        def commit_then_delete_elsewhere() -> None:
            real_commit()
            with SessionLocal() as other:
                other.execute(delete(Budget).where(Budget.user_id == user_id))
                other.commit()

        db.commit = commit_then_delete_elsewhere
        if write == "create":
            view = budget_service.create_budget(
                db, user_id, BudgetCreate(category="Pets", month="2026-10", amount="300")
            )
        else:
            view = budget_service.update_budget(db, user_id, budget_id, BudgetUpdate(amount="400"))

    # The pending pet expense of the fixture (189.90, due 2026-10-21) counts in October.
    assert view.spent == Decimal("189.90")
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Budget).where(Budget.user_id == user_id)) == 0


# --- any write vs. delete of the pet, in both orders -----------------------------------------------


def held(call: Call) -> Call:
    """Run a service call inside the holder transaction of `run_while_locked`, keeping its locks: its own
    commit only flushes, and `run_while_locked` commits once the other call has had time to wait."""

    def _lock(db: Session) -> object:
        real_commit = db.commit
        db.commit = db.flush
        try:
            return call(db)
        finally:
            db.commit = real_commit

    return _lock


def _create_with_mel(ids: Committed) -> Call:
    data = TransactionCreate(
        type="expense", amount="50", category="Pets", due_date="2026-10-22", pet_id=ids.mel_id
    )
    return lambda db: transaction_service.create_transaction(db, SETTINGS, ids.user_id, data)


def _pay(ids: Committed) -> Call:
    return lambda db: transaction_service.pay(db, SETTINGS, ids.user_id, ids.transaction_id, None)


def _delete_transaction(ids: Committed) -> Call:
    return lambda db: transaction_service.delete_transaction(
        db, FakeStorage(), ids.user_id, ids.transaction_id
    )


def _delete_mel(ids: Committed) -> Call:
    return lambda db: pet_service.delete_pet(db, FakeStorage(), ids.user_id, ids.mel_id)


def _mel_transactions(ids: Committed) -> list[Transaction]:
    with SessionLocal() as db:
        return list(db.scalars(select(Transaction).where(Transaction.user_id == ids.user_id)))


@pytest.mark.parametrize("pet_first", [True, False], ids=["delete-pet-first", "write-first"])
@pytest.mark.parametrize("write", ["create", "pay", "delete"])
def test_transaction_write_racing_a_pet_delete(committed, write, pet_first):
    ids = committed
    call = {"create": _create_with_mel, "pay": _pay, "delete": _delete_transaction}[write](ids)
    first, second = (_delete_mel(ids), call) if pet_first else (call, _delete_mel(ids))

    (outcome,), waited = run_while_locked(held(first), second)

    assert waited, "the second call should wait for the locks of the first"
    if write == "create" and pet_first:
        # The pet was gone when the POST got its lock: 422, never the foreign key error (500).
        assert isinstance(outcome, transaction_service.PetNotFound), repr(outcome)
    else:
        assert not isinstance(outcome, Exception), repr(outcome)
    stored = _mel_transactions(ids)
    assert all(tx.pet_id is None for tx in stored), "the deleted pet is still linked"
    expected = {"create": 1 if pet_first else 2, "pay": 1, "delete": 0}[write]
    assert len(stored) == expected
    if write == "pay":
        assert stored[0].paid_at is not None
