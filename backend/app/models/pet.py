import uuid
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, EntityMixin, in_check

if TYPE_CHECKING:
    from app.models.finance import Transaction


class PetEventType(StrEnum):
    VACCINE = "vaccine"
    VET = "vet"
    MEDICATION = "medication"
    GROOMING = "grooming"
    OTHER = "other"


class PetSort(StrEnum):
    """Accepted list orderings; a leading "-" means descending."""

    NAME = "name"
    NAME_DESC = "-name"
    CREATED_AT = "created_at"
    CREATED_AT_DESC = "-created_at"


class Pet(EntityMixin, Base):
    __tablename__ = "pets"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    species: Mapped[str] = mapped_column(String(50))
    breed: Mapped[str | None] = mapped_column(String(100))
    birth_date: Mapped[date | None]
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    notes: Mapped[str | None] = mapped_column(Text)

    events: Mapped[list["PetEvent"]] = relationship(
        back_populates="pet",
        primaryjoin="Pet.id == foreign(PetEvent.pet_id)",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    # Expenses survive the pet (pet_id becomes NULL in the database), so no delete cascade here.
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="pet",
        primaryjoin="Pet.id == foreign(Transaction.pet_id)",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint("weight_kg > 0", name="weight_kg_positive"),
        # Target of the composite FKs that keep pet_events/transactions on the pet owner's account.
        UniqueConstraint("id", "user_id"),
    )


class PetEvent(EntityMixin, Base):
    __tablename__ = "pet_events"

    pet_id: Mapped[uuid.UUID] = mapped_column(index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(20))
    occurred_on: Mapped[date]
    next_due_on: Mapped[date | None]
    description: Mapped[str | None] = mapped_column(Text)

    pet: Mapped[Pet] = relationship(back_populates="events", primaryjoin="Pet.id == foreign(PetEvent.pet_id)")

    __table_args__ = (
        ForeignKeyConstraint(["pet_id", "user_id"], ["pets.id", "pets.user_id"], ondelete="CASCADE"),
        CheckConstraint(in_check("type", PetEventType), name="type"),
        CheckConstraint("next_due_on IS NULL OR next_due_on >= occurred_on", name="next_due_after_occurred"),
        Index("ix_pet_events_user_id_next_due_on", "user_id", "next_due_on"),
    )
