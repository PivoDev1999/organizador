import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, Numeric, String, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, EntityMixin
from app.models.pantry import PantryItem


class ShoppingSort(StrEnum):
    """Accepted list orderings; a leading "-" means descending."""

    CATEGORY = "category"  # category, then name
    NAME = "name"
    NAME_DESC = "-name"
    CREATED_AT = "created_at"
    CREATED_AT_DESC = "-created_at"
    PURCHASED_AT_DESC = "-purchased_at"


class ShoppingItem(EntityMixin, Base):
    __tablename__ = "shopping_items"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    unit: Mapped[str | None] = mapped_column(String(20))
    category: Mapped[str] = mapped_column(String(100))
    estimated_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    is_purchased: Mapped[bool] = mapped_column(server_default=false())
    purchased_at: Mapped[datetime | None]
    pantry_item_id: Mapped[uuid.UUID | None] = mapped_column(index=True)

    pantry_item: Mapped[PantryItem | None] = relationship(
        back_populates="shopping_items", primaryjoin="PantryItem.id == foreign(ShoppingItem.pantry_item_id)"
    )

    __table_args__ = (
        # PostgreSQL 15+ column list: deleting the pantry item clears pantry_item_id only.
        ForeignKeyConstraint(
            ["pantry_item_id", "user_id"],
            ["pantry_items.id", "pantry_items.user_id"],
            ondelete="SET NULL (pantry_item_id)",
        ),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("estimated_price >= 0", name="estimated_price_non_negative"),
        CheckConstraint(
            "is_purchased = (purchased_at IS NOT NULL)", name="purchased_at_matches_is_purchased"
        ),
        Index("ix_shopping_items_user_id_is_purchased", "user_id", "is_purchased"),
    )
