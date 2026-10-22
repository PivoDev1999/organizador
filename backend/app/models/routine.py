import uuid
from datetime import date, time
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    true,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, EntityMixin, in_check


class RoutineFrequency(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class RoutineSort(StrEnum):
    """Accepted list orderings; a leading "-" means descending."""

    NAME = "name"
    NAME_DESC = "-name"
    CREATED_AT = "created_at"
    CREATED_AT_DESC = "-created_at"


# Each frequency uses exactly one way of saying "when": none, weekdays or a day of the month.
# The explicit IS NOT NULL matters: cardinality(NULL) is NULL, and a NULL CHECK result passes.
_SCHEDULE_CHECK = (
    "(frequency = 'daily' AND days_of_week IS NULL AND day_of_month IS NULL) OR "
    "(frequency = 'weekly' AND days_of_week IS NOT NULL AND cardinality(days_of_week) > 0 "
    "AND day_of_month IS NULL) OR "
    "(frequency = 'monthly' AND day_of_month IS NOT NULL AND days_of_week IS NULL)"
)


class Routine(EntityMixin, Base):
    __tablename__ = "routines"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    frequency: Mapped[str] = mapped_column(String(10))
    # 0 = Sunday ... 6 = Saturday (same as PostgreSQL's EXTRACT(DOW ...)).
    days_of_week: Mapped[list[int] | None] = mapped_column(ARRAY(SmallInteger))
    day_of_month: Mapped[int | None] = mapped_column(SmallInteger)
    time_of_day: Mapped[time | None]
    is_active: Mapped[bool] = mapped_column(server_default=true())

    logs: Mapped[list["RoutineLog"]] = relationship(
        back_populates="routine",
        primaryjoin="Routine.id == foreign(RoutineLog.routine_id)",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint(in_check("frequency", RoutineFrequency), name="frequency"),
        CheckConstraint("day_of_month BETWEEN 1 AND 31", name="day_of_month_range"),
        CheckConstraint("days_of_week <@ ARRAY[0, 1, 2, 3, 4, 5, 6]::smallint[]", name="days_of_week_range"),
        CheckConstraint("array_ndims(days_of_week) = 1", name="days_of_week_one_dimension"),
        CheckConstraint(_SCHEDULE_CHECK, name="schedule_matches_frequency"),
        # Target of the composite FK that keeps routine_logs.user_id equal to the routine's owner.
        UniqueConstraint("id", "user_id"),
    )


class RoutineLog(EntityMixin, Base):
    __tablename__ = "routine_logs"

    routine_id: Mapped[uuid.UUID]
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    done_on: Mapped[date]
    note: Mapped[str | None] = mapped_column(Text)

    # Joined on id only, so the ORM never writes user_id through this relationship.
    routine: Mapped[Routine] = relationship(
        back_populates="logs", primaryjoin="Routine.id == foreign(RoutineLog.routine_id)"
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["routine_id", "user_id"], ["routines.id", "routines.user_id"], ondelete="CASCADE"
        ),
        # Also serves as the index for routine_id lookups (leading column).
        UniqueConstraint("routine_id", "done_on"),
        Index("ix_routine_logs_user_id_done_on", "user_id", "done_on"),
    )
