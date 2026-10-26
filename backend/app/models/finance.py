import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, EntityMixin, in_check
from app.models.pet import Pet


class TransactionType(StrEnum):
    INCOME = "income"
    EXPENSE = "expense"


class TransactionSort(StrEnum):
    """Accepted list orderings; a leading "-" means descending."""

    DUE_DATE = "due_date"
    DUE_DATE_DESC = "-due_date"
    AMOUNT = "amount"
    AMOUNT_DESC = "-amount"
    CREATED_AT = "created_at"
    CREATED_AT_DESC = "-created_at"


class Transaction(EntityMixin, Base):
    __tablename__ = "transactions"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(10))
    # Always positive: the direction comes from `type`.
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    category: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(255))
    due_date: Mapped[date]
    paid_at: Mapped[datetime | None]
    pet_id: Mapped[uuid.UUID | None] = mapped_column(index=True)

    pet: Mapped[Pet | None] = relationship(
        back_populates="transactions", primaryjoin="Pet.id == foreign(Transaction.pet_id)"
    )

    __table_args__ = (
        # PostgreSQL 15+ column list: deleting the pet clears pet_id only, user_id must stay.
        ForeignKeyConstraint(
            ["pet_id", "user_id"], ["pets.id", "pets.user_id"], ondelete="SET NULL (pet_id)"
        ),
        CheckConstraint(in_check("type", TransactionType), name="type"),
        CheckConstraint("amount > 0", name="amount_positive"),
        Index("ix_transactions_user_id_due_date", "user_id", "due_date"),
        Index("ix_transactions_user_id_category", "user_id", "category"),
    )


class Budget(EntityMixin, Base):
    __tablename__ = "budgets"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(String(100))
    # Stored as the first day of the month (e.g. 2026-10-01).
    month: Mapped[date]
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))

    __table_args__ = (
        CheckConstraint("EXTRACT(DAY FROM month) = 1", name="month_first_day"),
        CheckConstraint("amount >= 0", name="amount_non_negative"),
        # Also covers user_id lookups (leading column).
        UniqueConstraint("user_id", "category", "month"),
    )
