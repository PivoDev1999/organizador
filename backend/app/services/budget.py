"""Monthly budgets per category.

A category has at most one budget per month, compared without case ("Mercado" = "mercado"). The
database UNIQUE (user_id, category, month) is case-sensitive, so creating and copying serialize on a
per-(user, month) advisory lock before checking (`budget_repo.lock_month`); the UNIQUE still catches
an identical spelling written by other means (409 as well).
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import Settings
from app.core.errors import ConflictError, NotFoundError
from app.core.finance import BudgetAlertLevel, budget_alert_level, month_of, percent_used
from app.models import Budget
from app.repositories import budget as budget_repo
from app.repositories.errors import DuplicateError
from app.schemas.finance import BudgetCreate, BudgetUpdate


class BudgetNotFound(NotFoundError):
    detail = "Orçamento não encontrado."


class BudgetExists(ConflictError):
    detail = "Já existe orçamento para essa categoria nesse mês."


@dataclass(frozen=True)
class BudgetView:
    budget: Budget
    spent: Decimal

    @property
    def remaining(self) -> Decimal:
        return self.budget.amount - self.spent

    @property
    def percent_used(self) -> Decimal | None:
        return percent_used(self.spent, self.budget.amount)


@dataclass(frozen=True)
class BudgetAlert:
    view: BudgetView
    level: BudgetAlertLevel


@dataclass(frozen=True)
class BudgetCopyResult:
    created: list[BudgetView]
    skipped: list[str]


def _views(
    db: Session, user_id: uuid.UUID, month: date, ids: list[uuid.UUID] | None = None
) -> list[BudgetView]:
    return [
        BudgetView(budget, spent) for budget, spent in budget_repo.list_with_spent(db, user_id, month, ids)
    ]


def _view(db: Session, budget: Budget) -> BudgetView:
    """The budget with what was spent. Writers call it before commit, while they still hold their
    locks: read after the commit, a budget deleted meanwhile by another device would be gone."""
    return BudgetView(budget, budget_repo.spent(db, budget.user_id, budget.category, budget.month))


def get_budget(db: Session, user_id: uuid.UUID, budget_id: uuid.UUID, *, for_update: bool = False) -> Budget:
    budget = budget_repo.get_for_user(db, user_id, budget_id, for_update=for_update)
    if budget is None:
        raise BudgetNotFound
    return budget


def list_budgets(db: Session, settings: Settings, user_id: uuid.UUID, month: date | None) -> list[BudgetView]:
    """Budgets of the month (default: the current one in the app timezone) with what was spent."""
    return _views(db, user_id, month or month_of(clock.today(settings.timezone)))


def _alert_order(alert: BudgetAlert) -> tuple[bool, Decimal]:
    """Exceeded first, then the exact share used (spent / amount, not the rounded percent). A zero
    budget with spending counts as infinitely used: first among the exceeded."""
    budget = alert.view.budget
    used = alert.view.spent / budget.amount if budget.amount else Decimal("Infinity")
    return alert.level != BudgetAlertLevel.EXCEEDED, -used


def list_alerts(db: Session, user_id: uuid.UUID, month: date) -> list[BudgetAlert]:
    """Budgets of the month in alert (`app.core.finance.budget_alert_level`, exact amounts): exceeded
    first, then the most used (exact share), then category in pt-BR (the order of the query; the sort
    is stable).

    The level is a pure Python rule, so the budgets of the month (a household has tens) are filtered here.
    """
    alerts = [
        BudgetAlert(view, level)
        for view in _views(db, user_id, month)
        if (level := budget_alert_level(view.spent, view.budget.amount)) is not None
    ]
    return sorted(alerts, key=_alert_order)


def create_budget(db: Session, user_id: uuid.UUID, data: BudgetCreate) -> BudgetView:
    budget_repo.lock_month(db, user_id, data.month)
    if budget_repo.category_exists(db, user_id, data.month, data.category):
        db.rollback()  # release the advisory lock now
        raise BudgetExists
    budget = Budget(user_id=user_id, **data.model_dump())
    try:
        budget_repo.add(db, budget)
    except DuplicateError:
        db.rollback()
        raise BudgetExists from None
    view = _view(db, budget)
    db.commit()
    return view


def update_budget(db: Session, user_id: uuid.UUID, budget_id: uuid.UUID, data: BudgetUpdate) -> BudgetView:
    """Only the amount changes, so the month lock is not needed: the row lock serializes the writers."""
    budget = get_budget(db, user_id, budget_id, for_update=True)
    if "amount" in data.model_fields_set and budget.amount != data.amount:
        budget.amount = data.amount
        budget_repo.save(db)
    view = _view(db, budget)
    db.commit()
    return view


def delete_budget(db: Session, user_id: uuid.UUID, budget_id: uuid.UUID) -> None:
    budget = get_budget(db, user_id, budget_id, for_update=True)
    budget_repo.delete(db, budget)
    db.commit()


def copy_budgets(db: Session, user_id: uuid.UUID, source: date, target: date) -> BudgetCopyResult:
    """Copy the budgets of `source` to `target`, skipping categories `target` already has (without case).

    Takes the same month lock as `create_budget` on `target`, so it cannot race a create (or another
    copy) into duplicates. `skipped` lists the source spellings.
    """
    budget_repo.lock_month(db, user_id, target)
    taken = {key for _, key in budget_repo.list_with_keys(db, user_id, target)}
    created: list[Budget] = []
    skipped: list[str] = []
    for budget, key in budget_repo.list_with_keys(db, user_id, source):
        if key in taken:
            skipped.append(budget.category)
            continue
        taken.add(key)
        created.append(Budget(user_id=user_id, category=budget.category, month=target, amount=budget.amount))
    if created:
        try:
            budget_repo.add_all(db, created)
        except DuplicateError:
            db.rollback()
            raise BudgetExists from None
    # Before commit, like `_view`: nothing deleted meanwhile can go missing from the answer.
    views = _views(db, user_id, target, [budget.id for budget in created]) if created else []
    db.commit()
    return BudgetCopyResult(created=views, skipped=skipped)
