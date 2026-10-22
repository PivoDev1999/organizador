"""Pure stock rules of the pantry: no database, no clock. The reference for SQL filters and tests alike.

`app.repositories.pantry` has the SQL twin of each rule; tests check that both agree.
"""

from datetime import date
from decimal import Decimal
from typing import Protocol


class StockItem(Protocol):
    quantity: Decimal
    min_quantity: Decimal | None
    expires_on: date | None


def is_low_stock(item: StockItem) -> bool:
    """At or below the minimum. Items without a minimum are never low."""
    return item.min_quantity is not None and item.quantity <= item.min_quantity


def is_expired(item: StockItem, today: date) -> bool:
    """Past its expiry date. Expiring today is not expired yet; no date means it does not expire."""
    return item.expires_on is not None and item.expires_on < today


def expires_by(item: StockItem, last_day: date) -> bool:
    """Expires on or before `last_day`, including items already expired."""
    return item.expires_on is not None and item.expires_on <= last_day


def shortfall(item: StockItem) -> Decimal | None:
    """How much is missing to get back to the minimum, or None when nothing is (no minimum, or at/above it).

    An item exactly at its minimum is low stock but has no shortfall.
    """
    if item.min_quantity is None or item.quantity >= item.min_quantity:
        return None
    return item.min_quantity - item.quantity


def same_unit(first: str | None, second: str | None) -> bool:
    """Units match ignoring case and surrounding spaces ("KG " and "kg"). A missing unit never matches."""
    if first is None or second is None:
        return False
    return first.strip().casefold() == second.strip().casefold()
