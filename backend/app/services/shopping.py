"""Lock order for pantry and shopping rows: ALWAYS the pantry item (P) first, then the shopping item (S).

Deleting a pantry item locks P and then, through the foreign key (ON DELETE SET NULL), every S linked
to it. Any service that locks both must follow the same P -> S order, or the two transactions can wait
for each other forever (Postgres then aborts one with a deadlock, a 409 via the global handler).
Inserting or re-linking S takes a FOR KEY SHARE on P (the foreign key check) and counts as locking P.
"""

import uuid
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, localcontext

from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import Settings
from app.core.errors import ConcurrentChangeError, ConflictError, NotFoundError, ValidationError
from app.core.stock import same_unit, shortfall
from app.models import PantryItem, ShoppingItem
from app.repositories import pantry as pantry_repo
from app.repositories import shopping as shopping_repo
from app.repositories.shopping import ShoppingFilters
from app.schemas.common import MONEY_PLACES, QUANTITY_MAX
from app.schemas.shopping import ShoppingItemCreate, ShoppingItemUpdate, ShoppingQuery

MONEY_STEP = Decimal(1).scaleb(-MONEY_PLACES)  # 0.01
# Attempts to lock P -> S when the item's link keeps changing between the read and the lock.
LOCK_ATTEMPTS = 3
# Enough digits to round any realistic sum of NUMERIC(10,3) x NUMERIC(12,2) products without overflow.
TOTAL_PRECISION = 60


class ShoppingItemNotFound(NotFoundError):
    detail = "Item da lista não encontrado."


class PantryItemNotFound(ValidationError):
    """The linked pantry item is missing or belongs to someone else: a 422 on the body, not a 404."""

    detail = "Item da despensa não encontrado."


class AlreadyPurchased(ConflictError):
    detail = "Item já comprado."


class NotPurchased(ConflictError):
    detail = "Item não está comprado."


class PendingItemExists(ConflictError):
    detail = "Já existe um item pendente na lista para este item da despensa."


class PantryStockLimitExceeded(ValidationError):
    detail = (
        f"A compra deixaria o estoque da despensa acima de {QUANTITY_MAX}. "
        "Ajuste a quantidade do item ou da despensa; nada foi registrado."
    )


@dataclass(frozen=True)
class PurchaseResult:
    item: ShoppingItem
    pantry_restocked: bool


@dataclass(frozen=True)
class ShoppingSummary:
    pending: int
    purchased: int
    estimated_total: Decimal


def list_items(db: Session, user_id: uuid.UUID, query: ShoppingQuery) -> tuple[list[ShoppingItem], int]:
    filters = ShoppingFilters(is_purchased=query.is_purchased, categories=query.category, search=query.q)
    return shopping_repo.list_for_user(db, user_id, filters, query.sort, query.limit, query.offset)


def get_item(
    db: Session, user_id: uuid.UUID, item_id: uuid.UUID, *, for_update: bool = False
) -> ShoppingItem:
    """The user's item. Someone else's item is reported as missing (404), never as forbidden."""
    item = shopping_repo.get_for_user(db, user_id, item_id, for_update=for_update)
    if item is None:
        raise ShoppingItemNotFound
    return item


def _check_pantry_item(db: Session, user_id: uuid.UUID, pantry_item_id: uuid.UUID | None) -> None:
    """A link must point to one of the user's pantry items (also enforced by the composite FK).

    Checked here so the client gets a 422 instead of a database error. The check holds a key-share
    lock on the pantry row until commit, so a concurrent delete cannot break the insert that follows.
    """
    if pantry_item_id is not None and not pantry_repo.exists_for_user(db, user_id, pantry_item_id):
        db.rollback()
        raise PantryItemNotFound


def create_item(db: Session, user_id: uuid.UUID, data: ShoppingItemCreate) -> ShoppingItem:
    _check_pantry_item(db, user_id, data.pantry_item_id)
    item = ShoppingItem(user_id=user_id, **data.model_dump())
    shopping_repo.add(db, item)
    db.commit()
    return item


def update_item(
    db: Session, user_id: uuid.UUID, item_id: uuid.UUID, data: ShoppingItemUpdate
) -> ShoppingItem:
    # Lock order P -> S: the new pantry item (key share) before the shopping item.
    if "pantry_item_id" in data.model_fields_set:
        _check_pantry_item(db, user_id, data.pantry_item_id)
    item = get_item(db, user_id, item_id, for_update=True)
    changes = {
        field: value
        for field, value in data.model_dump(exclude_unset=True).items()
        if getattr(item, field) != value
    }
    if changes:
        for field, value in changes.items():
            setattr(item, field, value)
        shopping_repo.save(db)
    # Without changes this only ends the transaction (no UPDATE, updated_at untouched) and releases
    # the row lock now.
    db.commit()
    return item


def delete_item(db: Session, user_id: uuid.UUID, item_id: uuid.UUID) -> None:
    item = get_item(db, user_id, item_id, for_update=True)
    shopping_repo.delete_item(db, item)
    db.commit()


def _lock_pantry_then_item(
    db: Session, user_id: uuid.UUID, item_id: uuid.UUID
) -> tuple[ShoppingItem, PantryItem | None]:
    """Lock the linked pantry item and then the shopping item (P -> S, see the module docstring).

    The link is only known after reading S, so S is read without a lock, P is locked, then S is locked
    and its link checked again. A link that changed in between (re-linked by a PATCH) means P was the
    wrong row: roll back and retry. A link that became NULL because P was deleted meanwhile is fine
    (P is gone, nothing to lock). After LOCK_ATTEMPTS changes in a row: 409.

    P is always locked FOR UPDATE: `purchase` changes its quantity, and `unpurchase` needs writers on
    the same P (another unpurchase, `from-pantry`) to run one after the other so its "no other pending
    item" check sees their commits. A shared lock would let two unpurchases check at the same time.
    """
    for _ in range(LOCK_ATTEMPTS):
        link = get_item(db, user_id, item_id).pantry_item_id
        pantry_item = None
        locked_link = None
        if link is not None:
            pantry_item = pantry_repo.get_for_user(db, user_id, link, for_update=True)
            locked_link = pantry_item.id if pantry_item is not None else None
        item = get_item(db, user_id, item_id, for_update=True)
        if item.pantry_item_id == locked_link:
            return item, pantry_item
        db.rollback()
    raise ConcurrentChangeError


def purchase(db: Session, user_id: uuid.UUID, item_id: uuid.UUID) -> PurchaseResult:
    """Mark the item as purchased and, when it is linked to the pantry, restock the pantry item.

    The pantry is restocked by the item's quantity only if the item has a quantity and its unit
    matches the pantry unit (ignoring case and spaces); otherwise only the purchase is recorded.
    Everything happens in one transaction: if the restock would exceed the pantry limit, it is a 422
    and nothing is saved, not even the purchase.

    Locks P then S (module docstring). A second concurrent purchase waits for the first and then gets
    the 409; a concurrent delete of the pantry item ends with the purchase recorded and the link NULL.
    """
    item, pantry_item = _lock_pantry_then_item(db, user_id, item_id)
    if item.is_purchased:
        db.rollback()  # release the row locks now
        raise AlreadyPurchased
    restocked = False
    if pantry_item is not None and item.quantity is not None and same_unit(item.unit, pantry_item.unit):
        new_quantity = pantry_item.quantity + item.quantity
        if new_quantity > QUANTITY_MAX:
            db.rollback()
            raise PantryStockLimitExceeded
        pantry_item.quantity = new_quantity
        restocked = True
    item.is_purchased = True
    item.purchased_at = clock.now_utc()
    shopping_repo.save(db)
    db.commit()
    return PurchaseResult(item, pantry_restocked=restocked)


def unpurchase(db: Session, user_id: uuid.UUID, item_id: uuid.UUID) -> ShoppingItem:
    """Put a purchased item back on the list (pending).

    The pantry is NOT touched: a restock done by the purchase stays (the stock is the source of truth
    and may have changed since). Adjust it in the pantry if needed.

    A linked item cannot go back to pending while another pending item is linked to the same pantry
    item (409), e.g. one created by `from-pantry` after the purchase: there is at most one pending
    item per pantry item for `from-pantry` and `unpurchase` (POST/PATCH may still add one on purpose).
    The FOR UPDATE lock on P (P -> S) makes this check wait for a running `from-pantry` or another
    `unpurchase` of the same pantry item until it commits.
    """
    item, _ = _lock_pantry_then_item(db, user_id, item_id)
    if not item.is_purchased:
        db.rollback()
        raise NotPurchased
    if item.pantry_item_id is not None and shopping_repo.pending_pantry_item_ids(
        db, user_id, [item.pantry_item_id]
    ):
        db.rollback()
        raise PendingItemExists
    item.is_purchased = False
    item.purchased_at = None
    shopping_repo.save(db)
    db.commit()
    return item


def get_summary(db: Session, user_id: uuid.UUID) -> ShoppingSummary:
    """Counts and the estimated total of the pending items (price is per unit; no quantity = 1 unit).

    The total is rounded to cents with ROUND_HALF_EVEN. It has no upper cap (it is a sum, not a stored
    value), so it may exceed the largest money input; the output type is unbounded instead of a 500.
    """
    totals = shopping_repo.totals(db, user_id)
    with localcontext() as context:
        context.prec = TOTAL_PRECISION
        total = totals.estimated_total.quantize(MONEY_STEP, rounding=ROUND_HALF_EVEN)
    return ShoppingSummary(pending=totals.pending, purchased=totals.purchased, estimated_total=total)


def create_from_pantry(
    db: Session, settings: Settings, user_id: uuid.UUID, *, include_expired: bool = False
) -> list[ShoppingItem]:
    """Add the low-stock pantry items (and the expired ones, when asked) to the list.

    Items that already have a pending shopping item linked are skipped, so calling it again creates
    nothing new. The suggested quantity is what is missing to reach the minimum (None when nothing is,
    e.g. exactly at the minimum or expired with enough stock). Returns only the created items.

    Concurrency: the candidate pantry rows are locked FOR UPDATE before checking the pending items. A
    second concurrent call waits for those locks and, once the first commits, its (separate) pending
    check sees the new items, so nothing is duplicated. The pending check must stay a separate
    statement: run after the lock, it gets a fresh snapshot.
    """
    expired_before = clock.today(settings.timezone) if include_expired else None
    candidates = pantry_repo.lock_shopping_candidates(db, user_id, expired_before)
    already_listed = shopping_repo.pending_pantry_item_ids(db, user_id, [item.id for item in candidates])
    created = [
        ShoppingItem(
            user_id=user_id,
            name=pantry_item.name,
            category=pantry_item.category,
            unit=pantry_item.unit,
            quantity=shortfall(pantry_item),
            pantry_item_id=pantry_item.id,
        )
        for pantry_item in candidates
        if pantry_item.id not in already_listed
    ]
    if created:
        shopping_repo.add_all(db, created)
    db.commit()
    return created


def delete_purchased(db: Session, user_id: uuid.UUID) -> int:
    deleted = shopping_repo.delete_purchased(db, user_id)
    db.commit()
    return deleted
