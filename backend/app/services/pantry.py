import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import Settings
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.stock import is_expired, is_low_stock
from app.models import PantryItem
from app.repositories import pantry as pantry_repo
from app.repositories.pantry import PantryFilters
from app.schemas.common import QUANTITY_MAX
from app.schemas.pantry import PantryItemCreate, PantryItemUpdate, PantryQuery, StockChange


class PantryItemNotFound(NotFoundError):
    detail = "Item não encontrado."


class InsufficientStock(ConflictError):
    detail = "Quantidade insuficiente."


class StockLimitExceeded(ValidationError):
    detail = f"A quantidade em estoque não pode passar de {QUANTITY_MAX}."


@dataclass(frozen=True)
class PantryItemView:
    """An item plus the flags computed for "today" in the app timezone."""

    item: PantryItem
    low_stock: bool
    expired: bool


@dataclass(frozen=True)
class PantryAlerts:
    low_stock: list[PantryItemView]
    expired: list[PantryItemView]
    expiring_soon: list[PantryItemView]


def _view(item: PantryItem, today: date) -> PantryItemView:
    return PantryItemView(item, low_stock=is_low_stock(item), expired=is_expired(item, today))


def _today(settings: Settings) -> date:
    return clock.today(settings.timezone)


def list_items(
    db: Session, settings: Settings, user_id: uuid.UUID, query: PantryQuery
) -> tuple[list[PantryItemView], int]:
    today = _today(settings)
    filters = PantryFilters(
        categories=query.category,
        location=query.location,
        search=query.q,
        low_stock=query.low_stock,
        expires_by=today + timedelta(days=query.expiring_within)
        if query.expiring_within is not None
        else None,
        # expired=false means "no expiry filter", not "only items that are not expired".
        expired_before=today if query.expired else None,
    )
    items, total = pantry_repo.list_for_user(db, user_id, filters, query.sort, query.limit, query.offset)
    return [_view(item, today) for item in items], total


def get_item(db: Session, user_id: uuid.UUID, item_id: uuid.UUID, *, for_update: bool = False) -> PantryItem:
    """The user's item. Someone else's item is reported as missing (404), never as forbidden."""
    item = pantry_repo.get_for_user(db, user_id, item_id, for_update=for_update)
    if item is None:
        raise PantryItemNotFound
    return item


def get_item_view(db: Session, settings: Settings, user_id: uuid.UUID, item_id: uuid.UUID) -> PantryItemView:
    return _view(get_item(db, user_id, item_id), _today(settings))


def create_item(
    db: Session, settings: Settings, user_id: uuid.UUID, data: PantryItemCreate
) -> PantryItemView:
    item = PantryItem(user_id=user_id, **data.model_dump())
    pantry_repo.add(db, item)
    db.commit()
    return _view(item, _today(settings))


def update_item(
    db: Session, settings: Settings, user_id: uuid.UUID, item_id: uuid.UUID, data: PantryItemUpdate
) -> PantryItemView:
    item = get_item(db, user_id, item_id, for_update=True)
    changes = {
        field: value
        for field, value in data.model_dump(exclude_unset=True).items()
        if getattr(item, field) != value
    }
    if changes:
        for field, value in changes.items():
            setattr(item, field, value)
        pantry_repo.save(db)
    # Without changes this only ends the transaction (no UPDATE, updated_at untouched) and releases
    # the row lock now, not after the response has been sent.
    db.commit()
    return _view(item, _today(settings))


def delete_item(db: Session, user_id: uuid.UUID, item_id: uuid.UUID) -> None:
    item = get_item(db, user_id, item_id, for_update=True)
    pantry_repo.delete(db, item)
    db.commit()


def consume(
    db: Session, settings: Settings, user_id: uuid.UUID, item_id: uuid.UUID, data: StockChange
) -> PantryItemView:
    """Take `amount` out of stock. More than what is stored is a 409: the stock must stay truthful.

    The row is locked until commit, so two phones consuming at once run one after the other and the
    second one decides on the quantity the first one left (no lost update, no negative stock).
    """
    item = get_item(db, user_id, item_id, for_update=True)
    if data.amount > item.quantity:
        db.rollback()  # release the row lock now
        raise InsufficientStock
    item.quantity = item.quantity - data.amount
    pantry_repo.save(db)
    db.commit()
    return _view(item, _today(settings))


def restock(
    db: Session, settings: Settings, user_id: uuid.UUID, item_id: uuid.UUID, data: StockChange
) -> PantryItemView:
    """Add `amount` to stock. A total beyond the column (NUMERIC(10,3)) is a 422, never a 500."""
    item = get_item(db, user_id, item_id, for_update=True)
    new_quantity = item.quantity + data.amount
    if new_quantity > QUANTITY_MAX:
        db.rollback()
        raise StockLimitExceeded
    item.quantity = new_quantity
    pantry_repo.save(db)
    db.commit()
    return _view(item, _today(settings))


def get_alerts(db: Session, settings: Settings, user_id: uuid.UUID, expiring_within: int) -> PantryAlerts:
    """Low stock, expired and expiring soon (today .. today + N), in two queries.

    One item may show up both in `low_stock` and in one of the expiry lists.
    """
    today = _today(settings)
    low_stock = [_view(item, today) for item in pantry_repo.list_low_stock(db, user_id)]
    by_expiry = [
        _view(item, today)
        for item in pantry_repo.list_expiring_by(db, user_id, today + timedelta(days=expiring_within))
    ]
    return PantryAlerts(
        low_stock=low_stock,
        expired=[view for view in by_expiry if view.expired],
        expiring_soon=[view for view in by_expiry if not view.expired],
    )


def list_categories(db: Session, user_id: uuid.UUID) -> list[str]:
    return pantry_repo.distinct_values(db, user_id, PantryItem.category)


def list_locations(db: Session, user_id: uuid.UUID) -> list[str]:
    return pantry_repo.distinct_values(db, user_id, PantryItem.location)
