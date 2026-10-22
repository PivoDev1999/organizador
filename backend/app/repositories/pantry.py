import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.models import PantryItem, PantrySort
from app.repositories.errors import flush
from app.repositories.search import LIKE_ESCAPE, TEXT_SORT_COLLATION, escape_like

# --- SQL twins of the pure rules in app.core.stock (tests check that both agree) ------------------


def low_stock_condition() -> ColumnElement[bool]:
    """SQL twin of `is_low_stock`."""
    return PantryItem.min_quantity.is_not(None) & (PantryItem.quantity <= PantryItem.min_quantity)


def expired_condition(today: date) -> ColumnElement[bool]:
    """SQL twin of `is_expired` (a NULL expires_on never matches)."""
    return PantryItem.expires_on < today


def expires_by_condition(last_day: date) -> ColumnElement[bool]:
    """SQL twin of `expires_by` (a NULL expires_on never matches)."""
    return PantryItem.expires_on <= last_day


@dataclass(frozen=True)
class PantryFilters:
    """Resolved list filters. Empty sequences and None mean "no filter"."""

    categories: Sequence[str] = ()
    location: str | None = None
    # Plain text, matched literally (case-insensitive) in the name.
    search: str | None = None
    low_stock: bool = False
    # When set: expires_on <= expires_by (already expired items included).
    expires_by: date | None = None
    # When set: expires_on < expired_before. The service passes "today" in the app timezone.
    expired_before: date | None = None


def _conditions(user_id: uuid.UUID, filters: PantryFilters) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [PantryItem.user_id == user_id]
    if filters.categories:
        conditions.append(PantryItem.category.in_(filters.categories))
    if filters.location is not None:
        conditions.append(PantryItem.location == filters.location)
    if filters.search is not None:
        conditions.append(PantryItem.name.ilike(f"%{escape_like(filters.search)}%", escape=LIKE_ESCAPE))
    if filters.low_stock:
        conditions.append(low_stock_condition())
    if filters.expires_by is not None:
        conditions.append(expires_by_condition(filters.expires_by))
    if filters.expired_before is not None:
        conditions.append(expired_condition(filters.expired_before))
    return conditions


def _sortable(column: InstrumentedAttribute[str]) -> ColumnElement[str]:
    return column.collate(TEXT_SORT_COLLATION)


def _order_by(sort: str) -> list[ColumnElement]:
    primary = {
        PantrySort.NAME: _sortable(PantryItem.name).asc(),
        PantrySort.NAME_DESC: _sortable(PantryItem.name).desc(),
        PantrySort.EXPIRES_ON: PantryItem.expires_on.asc().nulls_last(),
        PantrySort.EXPIRES_ON_DESC: PantryItem.expires_on.desc().nulls_last(),
        PantrySort.QUANTITY: PantryItem.quantity.asc(),
        PantrySort.QUANTITY_DESC: PantryItem.quantity.desc(),
        PantrySort.CREATED_AT: PantryItem.created_at.asc(),
        PantrySort.CREATED_AT_DESC: PantryItem.created_at.desc(),
    }[PantrySort(sort)]
    # `id` is unique, so the order is total and pages never repeat or skip rows.
    return [primary, PantryItem.id.asc()]


def get_for_user(
    db: Session, user_id: uuid.UUID, item_id: uuid.UUID, *, for_update: bool = False
) -> PantryItem | None:
    """The item if it belongs to the user.

    `for_update=True` locks the row (SELECT ... FOR UPDATE) and refreshes any copy already in the
    session, so read-modify-write (stock changes above all) decides on the latest committed row.
    See `task.get_for_user`.
    """
    stmt = select(PantryItem).where(PantryItem.id == item_id, PantryItem.user_id == user_id)
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return db.scalar(stmt)


def list_for_user(
    db: Session, user_id: uuid.UUID, filters: PantryFilters, sort: str, limit: int, offset: int
) -> tuple[list[PantryItem], int]:
    """One page of the user's items plus the total number of matches (same filters, no paging)."""
    conditions = _conditions(user_id, filters)
    total = db.scalar(select(func.count()).select_from(PantryItem).where(*conditions)) or 0
    items = db.scalars(
        select(PantryItem).where(*conditions).order_by(*_order_by(sort)).limit(limit).offset(offset)
    ).all()
    return list(items), total


def list_low_stock(db: Session, user_id: uuid.UUID) -> list[PantryItem]:
    """Every low-stock item of the user, by name (pt-BR) and id."""
    return list(
        db.scalars(
            select(PantryItem)
            .where(PantryItem.user_id == user_id, low_stock_condition())
            .order_by(*_order_by(PantrySort.NAME))
        ).all()
    )


def list_expiring_by(db: Session, user_id: uuid.UUID, last_day: date) -> list[PantryItem]:
    """Every item expiring on or before `last_day` (expired ones included), by expiry date, name, id."""
    return list(
        db.scalars(
            select(PantryItem)
            .where(PantryItem.user_id == user_id, expires_by_condition(last_day))
            .order_by(PantryItem.expires_on.asc(), _sortable(PantryItem.name).asc(), PantryItem.id.asc())
        ).all()
    )


def distinct_values(db: Session, user_id: uuid.UUID, column: InstrumentedAttribute[str | None]) -> list[str]:
    """Distinct non-null values of a text column among the user's items, sorted (pt-BR)."""
    # GROUP BY rather than DISTINCT: Postgres requires DISTINCT's ORDER BY expressions (here with
    # COLLATE) to appear in the select list.
    return list(
        db.scalars(
            select(column)
            .where(PantryItem.user_id == user_id, column.is_not(None))
            .group_by(column)
            .order_by(_sortable(column))
        ).all()
    )


def add(db: Session, item: PantryItem) -> PantryItem:
    """Insert and flush. The caller rolls back after an error."""
    db.add(item)
    flush(db)
    return item


def save(db: Session) -> None:
    """Flush pending changes of loaded items."""
    flush(db)


def delete(db: Session, item: PantryItem) -> None:
    """Delete the item. Linked shopping items stay, with pantry_item_id set to NULL by the database
    (ON DELETE SET NULL, passive_deletes)."""
    db.delete(item)
    flush(db)
