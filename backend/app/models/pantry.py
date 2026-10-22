import uuid
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, EntityMixin

if TYPE_CHECKING:
    from app.models.shopping import ShoppingItem


class PantrySort(StrEnum):
    """Accepted list orderings; a leading "-" means descending."""

    NAME = "name"
    NAME_DESC = "-name"
    EXPIRES_ON = "expires_on"
    EXPIRES_ON_DESC = "-expires_on"
    QUANTITY = "quantity"
    QUANTITY_DESC = "-quantity"
    CREATED_AT = "created_at"
    CREATED_AT_DESC = "-created_at"


class PantryItem(EntityMixin, Base):
    __tablename__ = "pantry_items"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(100))
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3), server_default="0")
    unit: Mapped[str] = mapped_column(String(20))
    min_quantity: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    expires_on: Mapped[date | None]
    location: Mapped[str | None] = mapped_column(String(100))

    # The database sets shopping_items.pantry_item_id to NULL; the ORM must not try to.
    shopping_items: Mapped[list["ShoppingItem"]] = relationship(
        back_populates="pantry_item",
        primaryjoin="PantryItem.id == foreign(ShoppingItem.pantry_item_id)",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint("quantity >= 0", name="quantity_non_negative"),
        CheckConstraint("min_quantity >= 0", name="min_quantity_non_negative"),
        Index("ix_pantry_items_user_id_expires_on", "user_id", "expires_on"),
        # Target of the composite FK that keeps shopping_items on the pantry owner's account.
        UniqueConstraint("id", "user_id"),
    )
