import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import ColumnElement, delete, func, literal, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.models import ShoppingItem, ShoppingSort
from app.repositories.errors import flush
from app.repositories.search import LIKE_ESCAPE, TEXT_SORT_COLLATION, escape_like


@dataclass(frozen=True)
class ShoppingFilters:
    """Resolved list filters. Empty sequences and None mean "no filter"."""

    is_purchased: bool | None = None
    categories: Sequence[str] = ()
    # Plain text, matched literally (case-insensitive) in the name.
    search: str | None = None


@dataclass(frozen=True)
class ShoppingTotals:
    pending: int
    purchased: int
    # Exact sum, not rounded (the service rounds it).
    estimated_total: Decimal


def _conditions(user_id: uuid.UUID, filters: ShoppingFilters) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [ShoppingItem.user_id == user_id]
    if filters.is_purchased is not None:
        conditions.append(ShoppingItem.is_purchased == filters.is_purchased)
    if filters.categories:
        conditions.append(ShoppingItem.category.in_(filters.categories))
    if filters.search is not None:
        conditions.append(ShoppingItem.name.ilike(f"%{escape_like(filters.search)}%", escape=LIKE_ESCAPE))
    return conditions


def _sortable(column: InstrumentedAttribute[str]) -> ColumnElement[str]:
    return column.collate(TEXT_SORT_COLLATION)


def _order_by(sort: str) -> list[ColumnElement]:
    primary = {
        ShoppingSort.CATEGORY: [_sortable(ShoppingItem.category).asc(), _sortable(ShoppingItem.name).asc()],
        ShoppingSort.NAME: [_sortable(ShoppingItem.name).asc()],
        ShoppingSort.NAME_DESC: [_sortable(ShoppingItem.name).desc()],
        ShoppingSort.CREATED_AT: [ShoppingItem.created_at.asc()],
        ShoppingSort.CREATED_AT_DESC: [ShoppingItem.created_at.desc()],
        ShoppingSort.PURCHASED_AT_DESC: [ShoppingItem.purchased_at.desc().nulls_last()],
    }[ShoppingSort(sort)]
    # `id` is unique, so the order is total and pages never repeat or skip rows.
    return [*primary, ShoppingItem.id.asc()]


def get_for_user(
    db: Session, user_id: uuid.UUID, item_id: uuid.UUID, *, for_update: bool = False
) -> ShoppingItem | None:
    """The item if it belongs to the user. `for_update=True` locks the row (see `pantry.get_for_user`)."""
    stmt = select(ShoppingItem).where(ShoppingItem.id == item_id, ShoppingItem.user_id == user_id)
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return db.scalar(stmt)


def list_for_user(
    db: Session, user_id: uuid.UUID, filters: ShoppingFilters, sort: str, limit: int, offset: int
) -> tuple[list[ShoppingItem], int]:
    """One page of the user's items plus the total number of matches (same filters, no paging)."""
    conditions = _conditions(user_id, filters)
    total = db.scalar(select(func.count()).select_from(ShoppingItem).where(*conditions)) or 0
    items = db.scalars(
        select(ShoppingItem).where(*conditions).order_by(*_order_by(sort)).limit(limit).offset(offset)
    ).all()
    return list(items), total


def totals(db: Session, user_id: uuid.UUID) -> ShoppingTotals:
    """Counts by state and the exact estimated total of the pending items, in one query.

    The total is SUM(COALESCE(quantity, 1) * estimated_price): NUMERIC arithmetic, exact and without
    the column cap; items without a price add nothing (NULL is ignored by SUM).
    """
    pending = ~ShoppingItem.is_purchased
    row = db.execute(
        select(
            func.count().filter(pending),
            func.count().filter(ShoppingItem.is_purchased),
            func.coalesce(
                func.sum(
                    func.coalesce(ShoppingItem.quantity, literal(1)) * ShoppingItem.estimated_price
                ).filter(pending),
                literal(0),
            ),
        ).where(ShoppingItem.user_id == user_id)
    ).one()
    return ShoppingTotals(pending=row[0], purchased=row[1], estimated_total=Decimal(row[2]))


def pending_pantry_item_ids(
    db: Session, user_id: uuid.UUID, pantry_item_ids: Collection[uuid.UUID]
) -> set[uuid.UUID]:
    """Which of the pantry items already have a pending shopping item linked to them."""
    if not pantry_item_ids:
        return set()
    return set(
        db.scalars(
            select(ShoppingItem.pantry_item_id).where(
                ShoppingItem.user_id == user_id,
                ShoppingItem.pantry_item_id.in_(pantry_item_ids),
                ~ShoppingItem.is_purchased,
            )
        ).all()
    )


def add(db: Session, item: ShoppingItem) -> ShoppingItem:
    """Insert and flush. The caller rolls back after an error."""
    db.add(item)
    flush(db)
    return item


def add_all(db: Session, items: Sequence[ShoppingItem]) -> None:
    """Insert several items in one flush."""
    db.add_all(items)
    flush(db)


def save(db: Session) -> None:
    """Flush pending changes of loaded items."""
    flush(db)


def delete_item(db: Session, item: ShoppingItem) -> None:
    db.delete(item)
    flush(db)


def delete_purchased(db: Session, user_id: uuid.UUID) -> int:
    """Delete every purchased item of the user; returns how many."""
    result = db.execute(
        delete(ShoppingItem).where(ShoppingItem.user_id == user_id, ShoppingItem.is_purchased)
    )
    return result.rowcount
