"""Transactions (contas a pagar e receitas).

Lock order: the pet first, then the transaction (see `app.repositories.transaction`). Creating or
re-linking a transaction checks the pet with `pet_repo.exists_for_user`, which holds a FOR KEY SHARE on
it until commit, before the transaction row is inserted or locked FOR UPDATE.

No re-check of the link is needed after the lock (unlike `shopping.purchase`, which finds the pantry
item to lock by reading the shopping item first): the pet to lock comes from the request body, not
from the stored row, and the KEY SHARE keeps it from being deleted until commit. The previous pet is
never locked: if it is deleted meanwhile, its ON DELETE SET NULL waits for this row lock and then
re-checks the row (it clears pet_id only if the row still points to that pet), or it committed first
and the locked read (populate_existing) already shows NULL.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import Settings
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.finance import (
    INCOME,
    CategoryTotals,
    MonthSummary,
    is_overdue,
    month_bounds,
    month_of,
    paid_at_for,
    paid_on_of,
)
from app.core.storage import Storage
from app.models import Transaction
from app.models.file import FileEntityType
from app.repositories import pet as pet_repo
from app.repositories import transaction as transaction_repo
from app.repositories.transaction import TransactionFilters
from app.schemas.finance import TransactionCreate, TransactionQuery, TransactionUpdate
from app.services import files as files_service


class TransactionNotFound(NotFoundError):
    detail = "Transação não encontrada."


class PetNotFound(ValidationError):
    """The linked pet is missing or belongs to someone else: a 422 on the body, not a 404."""

    detail = "Pet não encontrado."


class FuturePayment(ValidationError):
    detail = "A data de pagamento não pode ser no futuro."


class AlreadyPaid(ConflictError):
    detail = "Transação já paga."


class NotPaid(ConflictError):
    detail = "Transação não está paga."


@dataclass(frozen=True)
class TransactionView:
    transaction: Transaction
    paid_on: date | None
    overdue: bool


def _today(settings: Settings) -> date:
    return clock.today(settings.timezone)


def _view(transaction: Transaction, settings: Settings, today: date) -> TransactionView:
    return TransactionView(
        transaction,
        paid_on_of(transaction.paid_at, settings.timezone),
        is_overdue(transaction.due_date, transaction.paid_at, today),
    )


def _views(transactions: list[Transaction], settings: Settings) -> list[TransactionView]:
    today = _today(settings)
    return [_view(transaction, settings, today) for transaction in transactions]


def _check_pet(db: Session, user_id: uuid.UUID, pet_id: uuid.UUID | None) -> None:
    """A link must point to one of the user's pets (also enforced by the composite FK).

    Checked first so the client gets a 422 instead of a database error, and so the pet is locked
    (FOR KEY SHARE) before the transaction: pet -> transaction, the order of a pet delete.
    """
    if pet_id is not None and not pet_repo.exists_for_user(db, user_id, pet_id):
        db.rollback()
        raise PetNotFound


def _paid_at(paid_on: date | None, settings: Settings) -> datetime:
    """Instant to store for a payment on the local date `paid_on` (None: today). Future: 422.

    Reads the clock once, so "today" for the check and for the conversion is the same day.
    """
    now = clock.now_utc()
    today = clock.today(settings.timezone, now)
    if paid_on is None:
        paid_on = today
    elif paid_on > today:
        raise FuturePayment
    return paid_at_for(paid_on, settings.timezone, now)


def get_transaction(
    db: Session, user_id: uuid.UUID, transaction_id: uuid.UUID, *, for_update: bool = False
) -> Transaction:
    """The user's transaction. Someone else's is reported as missing (404), never as forbidden."""
    transaction = transaction_repo.get_for_user(db, user_id, transaction_id, for_update=for_update)
    if transaction is None:
        raise TransactionNotFound
    return transaction


def get_view(
    db: Session, settings: Settings, user_id: uuid.UUID, transaction_id: uuid.UUID
) -> TransactionView:
    return _view(get_transaction(db, user_id, transaction_id), settings, _today(settings))


def list_transactions(
    db: Session, settings: Settings, user_id: uuid.UUID, query: TransactionQuery
) -> tuple[list[TransactionView], int]:
    due_from, due_to = query.due_from, query.due_to
    if query.month is not None:
        due_from, due_to = month_bounds(query.month)
    filters = TransactionFilters(
        types=query.type,
        categories=query.category,
        statuses=query.status,
        today=_today(settings),
        due_from=due_from,
        due_to=due_to,
        pet_id=query.pet_id,
        search=query.q,
    )
    items, total = transaction_repo.list_for_user(db, user_id, filters, query.sort, query.limit, query.offset)
    return _views(items, settings), total


def list_upcoming(db: Session, settings: Settings, user_id: uuid.UUID, within: int) -> list[TransactionView]:
    """Pending expenses due up to today + `within` days, overdue ones included."""
    today = _today(settings)
    items = transaction_repo.list_upcoming(db, user_id, today + timedelta(days=within))
    return [_view(item, settings, today) for item in items]


def list_categories(db: Session, user_id: uuid.UUID) -> list[str]:
    return transaction_repo.distinct_categories(db, user_id)


def create_transaction(
    db: Session, settings: Settings, user_id: uuid.UUID, data: TransactionCreate
) -> TransactionView:
    fields = data.model_dump(exclude={"paid_on"})
    if data.paid_on is not None:
        fields["paid_at"] = _paid_at(data.paid_on, settings)
    _check_pet(db, user_id, data.pet_id)
    # user_id always comes from the authenticated user; the composite FK ties it to the pet owner.
    transaction = Transaction(user_id=user_id, **fields)
    transaction_repo.add(db, transaction)
    db.commit()
    return _view(transaction, settings, _today(settings))


def update_transaction(
    db: Session, settings: Settings, user_id: uuid.UUID, transaction_id: uuid.UUID, data: TransactionUpdate
) -> TransactionView:
    # Pet before transaction (module docstring). Also when the same pet is sent again (a form that
    # sends every field): locking it after the transaction would deadlock with a delete of that pet.
    if "pet_id" in data.model_fields_set:
        _check_pet(db, user_id, data.pet_id)
    transaction = get_transaction(db, user_id, transaction_id, for_update=True)
    changes = {
        field: value
        for field, value in data.model_dump(exclude_unset=True).items()
        if getattr(transaction, field) != value
    }
    if changes:
        for field, value in changes.items():
            setattr(transaction, field, value)
        transaction_repo.save(db)
    # Without changes this only ends the transaction (no UPDATE, updated_at untouched) and releases
    # the locks now.
    db.commit()
    return _view(transaction, settings, _today(settings))


def delete_transaction(db: Session, storage: Storage, user_id: uuid.UUID, transaction_id: uuid.UUID) -> None:
    transaction = get_transaction(db, user_id, transaction_id, for_update=True)
    transaction_repo.delete(db, transaction)
    keys = files_service.delete_attachments(db, user_id, FileEntityType.TRANSACTION, [transaction_id])
    db.commit()
    files_service.purge_objects(storage, keys)


def pay(
    db: Session, settings: Settings, user_id: uuid.UUID, transaction_id: uuid.UUID, paid_on: date | None
) -> TransactionView:
    """Mark as paid on `paid_on` (default: today in the app timezone). Already paid: 409.

    The row lock makes a second concurrent payment wait and then see the first one (409).
    """
    paid_at = _paid_at(paid_on, settings)
    transaction = get_transaction(db, user_id, transaction_id, for_update=True)
    if transaction.paid_at is not None:
        db.rollback()  # release the row lock now
        raise AlreadyPaid
    transaction.paid_at = paid_at
    transaction_repo.save(db)
    db.commit()
    return _view(transaction, settings, _today(settings))


def unpay(db: Session, settings: Settings, user_id: uuid.UUID, transaction_id: uuid.UUID) -> TransactionView:
    """Back to pending. Not paid: 409."""
    transaction = get_transaction(db, user_id, transaction_id, for_update=True)
    if transaction.paid_at is None:
        db.rollback()
        raise NotPaid
    transaction.paid_at = None
    transaction_repo.save(db)
    db.commit()
    return _view(transaction, settings, _today(settings))


def get_summary(db: Session, settings: Settings, user_id: uuid.UUID, month: date | None) -> MonthSummary:
    """Totals of the month (default: the current one) on the accrual basis; see `app.core.finance`.

    The sums are exact NUMERIC sums done by the database; the pure `finance.summarize` is their
    reference (tests check that both agree).
    """
    first, last = month_bounds(month or month_of(_today(settings)))
    summary = MonthSummary(month=first)
    for row in transaction_repo.month_totals(db, user_id, first, last):
        totals = summary.income if row.type == INCOME else summary.expense
        totals.total, totals.paid, totals.pending = row.total, row.paid, row.pending
    summary.by_category = [
        CategoryTotals(
            total=row.total, paid=row.paid, pending=row.pending, type=row.type, category=row.category
        )
        for row in transaction_repo.category_totals(db, user_id, first, last)
    ]
    return summary
