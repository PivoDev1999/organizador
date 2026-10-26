"""Pure finance rules: no database, no clock. The reference for the SQL in the repositories and for tests.

Accrual basis (regime de competência): a transaction belongs to the month of its `due_date`, paid or
not. The monthly summary and the "spent" of a budget both follow it.

Categories are compared without case: the key is `str.lower()`. The repositories use the SQL twin
`lower(category COLLATE "pt-BR-x-icu")`; ICU's lower case is the full Unicode mapping, like Python's
(the database default collation, musl's en_US, is not). Accents still count ("Saude" and "Saúde" are
different categories) and so does whitespace (the API stores categories trimmed). `casefold()` is not
used: it has no SQL twin.

Spelling shown for a group of categories that only differ in case (summary `by_category`, the list of
categories): the one of the most recently created transaction (`created_at`, then `id`), so renaming
"mercado" to "Mercado" in new entries changes how the group is shown.

`paid_on` (a local date, what people type) -> `paid_at` (an instant, what is stored): paying "today"
records the current instant; any other day records noon of that day in the app timezone, converted to
UTC. Noon is far from both midnights, so converting back with the same timezone always gives the same
day, even across a DST change. `paid_on` in the responses is `paid_at` seen in the app timezone.
"""

import uuid
from calendar import monthrange
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Protocol
from zoneinfo import ZoneInfo

# Earliest accepted payment and due dates. Far enough back for any real bill, and it keeps the
# local-noon conversion of `paid_at_for` away from datetime's year-1 limit: in a UTC+13 zone (e.g.
# Pacific/Apia) noon of 0001-01-01 is before 0001-01-01 00:00 UTC, an OverflowError.
MIN_PAID_ON = date(2000, 1, 1)
# Same floor for due dates: nothing overflows there, but a due date before 2000 is a typo, and keeping
# both on one floor means a transaction can always be paid on its due date.
MIN_DUE_DATE = MIN_PAID_ON
ZERO = Decimal("0.00")
PERCENT_STEP = Decimal("0.1")
PAID_AT_LOCAL_TIME = time(12, 0)
INCOME, EXPENSE = "income", "expense"


class TransactionStatus(StrEnum):
    PENDING = "pending"  # not paid yet (overdue ones included)
    PAID = "paid"
    OVERDUE = "overdue"  # pending with due_date before today


class Entry(Protocol):
    """What the rules need from a transaction (the ORM Transaction fits)."""

    id: uuid.UUID
    type: str
    amount: Decimal
    category: str
    due_date: date
    paid_at: datetime | None
    created_at: datetime


# --- dates ----------------------------------------------------------------------------------------


def month_bounds(month: date) -> tuple[date, date]:
    """First and last day of the month of `month` (inclusive). Safe for December 9999."""
    return month.replace(day=1), month.replace(day=monthrange(month.year, month.month)[1])


def month_of(day: date) -> date:
    return day.replace(day=1)


def paid_at_for(paid_on: date, tz: ZoneInfo, now: datetime) -> datetime:
    """Instant stored for a payment made on the local date `paid_on` (see the module docstring).

    `paid_on` must not be before MIN_PAID_ON (the API rejects it): near year 1 the conversion overflows.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if paid_on == now.astimezone(tz).date():
        return now
    return datetime.combine(paid_on, PAID_AT_LOCAL_TIME, tzinfo=tz).astimezone(now.tzinfo)


def paid_on_of(paid_at: datetime | None, tz: ZoneInfo) -> date | None:
    """Local date of a payment."""
    return None if paid_at is None else paid_at.astimezone(tz).date()


def is_overdue(due_date: date, paid_at: datetime | None, today: date) -> bool:
    """Pending and due before today. Due today is not overdue yet."""
    return paid_at is None and due_date < today


def has_status(entry: Entry, status: TransactionStatus, today: date) -> bool:
    if status is TransactionStatus.PAID:
        return entry.paid_at is not None
    if status is TransactionStatus.PENDING:
        return entry.paid_at is None
    return is_overdue(entry.due_date, entry.paid_at, today)


# --- categories -----------------------------------------------------------------------------------


def category_key(category: str) -> str:
    """Categories with the same key are the same category."""
    return category.lower()


def _recency(entry: Entry) -> tuple[datetime, uuid.UUID]:
    return entry.created_at, entry.id


# --- monthly summary ------------------------------------------------------------------------------


@dataclass
class Totals:
    total: Decimal = ZERO
    paid: Decimal = ZERO
    pending: Decimal = ZERO

    def add(self, amount: Decimal, paid: bool) -> None:
        self.total += amount
        if paid:
            self.paid += amount
        else:
            self.pending += amount


@dataclass
class CategoryTotals(Totals):
    type: str = EXPENSE
    category: str = ""


@dataclass
class MonthSummary:
    month: date
    income: Totals = field(default_factory=Totals)
    expense: Totals = field(default_factory=Totals)
    by_category: list[CategoryTotals] = field(default_factory=list)

    @property
    def balance_total(self) -> Decimal:
        return self.income.total - self.expense.total

    @property
    def balance_paid(self) -> Decimal:
        return self.income.paid - self.expense.paid


def summarize(entries: Iterable[Entry], month: date) -> MonthSummary:
    """Income and expense totals of the month (accrual basis) and the totals per (type, category).

    `by_category` is ordered by type (expense first), then by the largest total; ties come in no
    particular order here (the endpoint breaks them by category in pt-BR, an ICU collation).
    """
    first, last = month_bounds(month)
    summary = MonthSummary(month=first)
    groups: dict[tuple[str, str], tuple[CategoryTotals, Entry]] = {}
    for entry in entries:
        if not first <= entry.due_date <= last:
            continue
        paid = entry.paid_at is not None
        (summary.income if entry.type == INCOME else summary.expense).add(entry.amount, paid)
        key = (entry.type, category_key(entry.category))
        totals, newest = groups.get(key, (CategoryTotals(type=entry.type), entry))
        if _recency(entry) >= _recency(newest):
            newest = entry
        totals.category = newest.category
        totals.add(entry.amount, paid)
        groups[key] = (totals, newest)
    summary.by_category = sorted(
        (totals for totals, _ in groups.values()), key=lambda item: (item.type, -item.total)
    )
    return summary


# --- budgets --------------------------------------------------------------------------------------


def budget_spent(entries: Iterable[Entry], category: str, month: date) -> Decimal:
    """Expenses of the month (accrual basis, paid or not) in the category, without case."""
    first, last = month_bounds(month)
    key = category_key(category)
    return sum(
        (
            entry.amount
            for entry in entries
            if entry.type == EXPENSE
            and first <= entry.due_date <= last
            and category_key(entry.category) == key
        ),
        ZERO,
    )


def percent_used(spent: Decimal, amount: Decimal) -> Decimal | None:
    """spent / amount in percent with 1 decimal place (half up). None for a zero budget: any spending
    would be "infinite" percent, and 0 of 0 is not 0% used either."""
    if amount == 0:
        return None
    return (spent * 100 / amount).quantize(PERCENT_STEP, rounding=ROUND_HALF_UP)
