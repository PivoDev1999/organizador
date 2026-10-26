import uuid
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, Integer, Select, cast, func, literal, select
from sqlalchemy.orm import Session

from app.core.finance import month_bounds
from app.models import Budget, Transaction, TransactionType
from app.repositories import transaction as transaction_repo
from app.repositories.errors import flush
from app.repositories.search import TEXT_SORT_COLLATION, case_insensitive_key

# Namespace of the advisory locks taken here, hashed with the user id (see `lock_month`).
ADVISORY_LOCK_NAMESPACE = "budgets"


def category_key() -> ColumnElement[str]:
    """SQL twin of `app.core.finance.category_key` for budgets."""
    return case_insensitive_key(Budget.category)


def lock_month(db: Session, user_id: uuid.UUID, month: date) -> None:
    """Serialize the budget writes of one user in one month until commit (transaction-level advisory lock).

    The UNIQUE (user_id, category, month) constraint is case-sensitive, so it does not stop "Mercado" and
    "mercado" from being created by two concurrent requests that both checked before either inserted.
    Creating and copying take this lock before checking, so the second one waits and then sees the
    first one's row. Key: (hashtext("budgets:<user_id>"), YYYYMM) in the two-int4 form; a hash
    collision between two users only makes them wait for each other, never mixes their data.

    The structural fix is a unique index on (user_id, lower(category COLLATE "pt-BR-x-icu"), month),
    which needs a migration.
    """
    db.execute(
        select(
            func.pg_advisory_xact_lock(
                func.hashtext(f"{ADVISORY_LOCK_NAMESPACE}:{user_id}"),
                cast(literal(month.year * 100 + month.month), Integer),
            )
        )
    )


def _expenses_in(month: date, user_id: Any, category: ColumnElement[str]) -> Select[tuple[Decimal]]:
    """Sum of the expenses due in `month` (accrual basis, paid or not) whose category matches `category`
    without case. SQL twin of `app.core.finance.budget_spent`."""
    first, last = month_bounds(month)
    return select(func.coalesce(func.sum(Transaction.amount), literal(0))).where(
        Transaction.user_id == user_id,
        Transaction.type == TransactionType.EXPENSE.value,
        Transaction.due_date.between(first, last),
        transaction_repo.category_key() == case_insensitive_key(category),
    )


def _spent(month: date) -> ColumnElement[Decimal]:
    """Correlated: what each budget row of `month` has spent."""
    return _expenses_in(month, Budget.user_id, Budget.category).correlate(Budget).scalar_subquery()


def spent(db: Session, user_id: uuid.UUID, category: str, month: date) -> Decimal:
    """What was spent in the category (without case) in the month."""
    return Decimal(db.scalar(_expenses_in(month, user_id, category)))


def list_with_spent(
    db: Session, user_id: uuid.UUID, month: date, ids: Sequence[uuid.UUID] | None = None
) -> list[tuple[Budget, Decimal]]:
    """The user's budgets of the month (only `ids`, when given) with what was spent, by category (pt-BR)."""
    stmt = select(Budget, _spent(month)).where(Budget.user_id == user_id, Budget.month == month)
    if ids is not None:
        stmt = stmt.where(Budget.id.in_(ids))
    rows = db.execute(stmt.order_by(Budget.category.collate(TEXT_SORT_COLLATION), Budget.id)).all()
    return [(row[0], Decimal(row[1])) for row in rows]


def get_for_user(
    db: Session, user_id: uuid.UUID, budget_id: uuid.UUID, *, for_update: bool = False
) -> Budget | None:
    """The budget if it belongs to the user. `for_update=True` locks the row (see `task.get_for_user`)."""
    stmt = select(Budget).where(Budget.id == budget_id, Budget.user_id == user_id)
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return db.scalar(stmt)


def category_exists(db: Session, user_id: uuid.UUID, month: date, category: str) -> bool:
    """Whether the user already has a budget for the category (without case) in the month."""
    stmt = select(Budget.id).where(
        Budget.user_id == user_id, Budget.month == month, category_key() == case_insensitive_key(category)
    )
    return db.scalar(stmt.limit(1)) is not None


def list_with_keys(db: Session, user_id: uuid.UUID, month: date) -> list[tuple[Budget, str]]:
    """The user's budgets of the month, each with its category key, by category (pt-BR)."""
    rows = db.execute(
        select(Budget, category_key())
        .where(Budget.user_id == user_id, Budget.month == month)
        .order_by(Budget.category.collate(TEXT_SORT_COLLATION), Budget.id)
    ).all()
    return [(row[0], row[1]) for row in rows]


def add(db: Session, budget: Budget) -> Budget:
    """Insert and flush. Raises DuplicateError for the (case-sensitive) unique constraint."""
    db.add(budget)
    flush(db)
    return budget


def add_all(db: Session, budgets: Sequence[Budget]) -> None:
    db.add_all(budgets)
    flush(db)


def save(db: Session) -> None:
    flush(db)


def delete(db: Session, budget: Budget) -> None:
    db.delete(budget)
    flush(db)
