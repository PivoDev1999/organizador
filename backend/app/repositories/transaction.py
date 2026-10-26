"""Transactions. Lock order with pets: ALWAYS the pet first, then the transaction.

Deleting a pet locks it (FOR UPDATE) and then, through the foreign key (ON DELETE SET NULL (pet_id)),
every transaction linked to it. Writes that set `pet_id` take a FOR KEY SHARE on the pet
(`pet.exists_for_user`) before locking the transaction, so both follow pet -> transaction.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import ColumnElement, String, case, func, literal, or_, select, type_coerce
from sqlalchemy.dialects.postgresql import ARRAY, aggregate_order_by
from sqlalchemy.orm import Session

from app.core.finance import TransactionStatus
from app.models import Transaction, TransactionSort, TransactionType
from app.repositories.errors import flush
from app.repositories.search import LIKE_ESCAPE, TEXT_SORT_COLLATION, case_insensitive_key, escape_like


@dataclass(frozen=True)
class TransactionFilters:
    """Resolved list filters. Empty sequences and None mean "no filter"."""

    types: Sequence[str] = ()
    # Compared without case (ICU lower case on both sides).
    categories: Sequence[str] = ()
    # Combined with OR. `today` (app timezone) is required when OVERDUE is among them.
    statuses: Sequence[str] = ()
    today: date | None = None
    # Inclusive bounds on due_date.
    due_from: date | None = None
    due_to: date | None = None
    pet_id: uuid.UUID | None = None
    # Plain text, matched literally (case-insensitive) in the description.
    search: str | None = None


@dataclass(frozen=True)
class TotalsRow:
    type: str
    category: str  # spelling of the newest transaction of the group (by_category only)
    total: Decimal
    paid: Decimal
    pending: Decimal


def category_key() -> ColumnElement[str]:
    """SQL twin of `app.core.finance.category_key`."""
    return case_insensitive_key(Transaction.category)


def _status_condition(status: str, today: date | None) -> ColumnElement[bool]:
    pending = Transaction.paid_at.is_(None)
    if status == TransactionStatus.PAID:
        return Transaction.paid_at.is_not(None)
    if status == TransactionStatus.PENDING:
        return pending
    if today is None:
        raise ValueError("today is required for the overdue status")
    return pending & (Transaction.due_date < today)


def _conditions(user_id: uuid.UUID, filters: TransactionFilters) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [Transaction.user_id == user_id]
    if filters.types:
        conditions.append(Transaction.type.in_(filters.types))
    if filters.categories:
        conditions.append(category_key().in_([case_insensitive_key(c) for c in filters.categories]))
    if filters.statuses:
        conditions.append(or_(*(_status_condition(s, filters.today) for s in filters.statuses)))
    if filters.due_from is not None:
        conditions.append(Transaction.due_date >= filters.due_from)
    if filters.due_to is not None:
        conditions.append(Transaction.due_date <= filters.due_to)
    if filters.pet_id is not None:
        conditions.append(Transaction.pet_id == filters.pet_id)
    if filters.search is not None:
        conditions.append(
            Transaction.description.ilike(f"%{escape_like(filters.search)}%", escape=LIKE_ESCAPE)
        )
    return conditions


def _order_by(sort: str) -> list[ColumnElement]:
    primary = {
        TransactionSort.DUE_DATE: Transaction.due_date.asc(),
        TransactionSort.DUE_DATE_DESC: Transaction.due_date.desc(),
        TransactionSort.AMOUNT: Transaction.amount.asc(),
        TransactionSort.AMOUNT_DESC: Transaction.amount.desc(),
        TransactionSort.CREATED_AT: Transaction.created_at.asc(),
        TransactionSort.CREATED_AT_DESC: Transaction.created_at.desc(),
    }[TransactionSort(sort)]
    # `id` is unique, so the order is total and pages never repeat or skip rows.
    return [primary, Transaction.id.asc()]


def get_for_user(
    db: Session, user_id: uuid.UUID, transaction_id: uuid.UUID, *, for_update: bool = False
) -> Transaction | None:
    """The transaction if it belongs to the user. `for_update=True` locks the row and refreshes any
    copy already in the session (see `task.get_for_user`)."""
    stmt = select(Transaction).where(Transaction.id == transaction_id, Transaction.user_id == user_id)
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return db.scalar(stmt)


def list_for_user(
    db: Session, user_id: uuid.UUID, filters: TransactionFilters, sort: str, limit: int, offset: int
) -> tuple[list[Transaction], int]:
    """One page of the user's transactions plus the total number of matches (same filters, no paging)."""
    conditions = _conditions(user_id, filters)
    total = db.scalar(select(func.count()).select_from(Transaction).where(*conditions)) or 0
    items = db.scalars(
        select(Transaction).where(*conditions).order_by(*_order_by(sort)).limit(limit).offset(offset)
    ).all()
    return list(items), total


def list_upcoming(db: Session, user_id: uuid.UUID, last_day: date) -> list[Transaction]:
    """Pending expenses due up to `last_day` (overdue ones included), by due date and id."""
    return list(
        db.scalars(
            select(Transaction)
            .where(
                Transaction.user_id == user_id,
                Transaction.type == TransactionType.EXPENSE.value,
                Transaction.paid_at.is_(None),
                Transaction.due_date <= last_day,
            )
            .order_by(Transaction.due_date.asc(), Transaction.id.asc())
        ).all()
    )


def _sums() -> list[ColumnElement]:
    paid = Transaction.paid_at.is_not(None)
    zero = literal(0)
    return [
        func.coalesce(func.sum(Transaction.amount), zero),
        func.coalesce(func.sum(Transaction.amount).filter(paid), zero),
        func.coalesce(func.sum(Transaction.amount).filter(~paid), zero),
    ]


def _newest_spelling() -> ColumnElement[str]:
    # (array_agg(category ORDER BY created_at DESC, id DESC))[1]: the newest spelling of the group.
    aggregated = type_coerce(
        func.array_agg(
            aggregate_order_by(Transaction.category, Transaction.created_at.desc(), Transaction.id.desc())
        ),
        ARRAY(String),
    )
    return aggregated[1]


def month_totals(db: Session, user_id: uuid.UUID, first: date, last: date) -> list[TotalsRow]:
    """Per type: exact NUMERIC sums (total, paid, pending) of the transactions due in [first, last]."""
    rows = db.execute(
        select(Transaction.type, *_sums())
        .where(Transaction.user_id == user_id, Transaction.due_date.between(first, last))
        .group_by(Transaction.type)
    ).all()
    return [TotalsRow(row[0], "", Decimal(row[1]), Decimal(row[2]), Decimal(row[3])) for row in rows]


def category_totals(db: Session, user_id: uuid.UUID, first: date, last: date) -> list[TotalsRow]:
    """Per (type, category without case): sums of the transactions due in [first, last].

    Expenses first, then the largest total, then the category in pt-BR order.
    """
    key = category_key()
    spelling = _newest_spelling()
    total = func.coalesce(func.sum(Transaction.amount), literal(0))
    # Explicit, not the alphabetical accident 'expense' < 'income'.
    expenses_first = case((Transaction.type == TransactionType.EXPENSE.value, 0), else_=1)
    rows = db.execute(
        select(Transaction.type, spelling, *_sums())
        .where(Transaction.user_id == user_id, Transaction.due_date.between(first, last))
        .group_by(Transaction.type, key)
        .order_by(expenses_first, total.desc(), spelling.collate(TEXT_SORT_COLLATION).asc())
    ).all()
    return [TotalsRow(row[0], row[1], Decimal(row[2]), Decimal(row[3]), Decimal(row[4])) for row in rows]


def distinct_categories(db: Session, user_id: uuid.UUID) -> list[str]:
    """The user's categories without case repetitions (newest spelling), sorted in pt-BR."""
    spelling = _newest_spelling()
    return list(
        db.scalars(
            select(spelling)
            .where(Transaction.user_id == user_id)
            .group_by(category_key())
            .order_by(spelling.collate(TEXT_SORT_COLLATION))
        ).all()
    )


def add(db: Session, transaction: Transaction) -> Transaction:
    """Insert and flush. The caller rolls back after an error."""
    db.add(transaction)
    flush(db)
    return transaction


def save(db: Session) -> None:
    """Flush pending changes of loaded transactions."""
    flush(db)


def delete(db: Session, transaction: Transaction) -> None:
    db.delete(transaction)
    flush(db)
