import uuid
from datetime import date, time
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, EntityMixin, in_check


class EventRecurrence(StrEnum):
    NONE = "none"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class Event(EntityMixin, Base):
    """Agenda entry on a single day. No start_time means an all-day event; recurring events repeat
    from starts_on until repeat_until (inclusive) or forever when it is NULL."""

    __tablename__ = "events"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(200))
    starts_on: Mapped[date]
    start_time: Mapped[time | None]
    end_time: Mapped[time | None]
    recurrence: Mapped[str] = mapped_column(String(10), server_default=EventRecurrence.NONE.value)
    repeat_until: Mapped[date | None]

    __table_args__ = (
        CheckConstraint(in_check("recurrence", EventRecurrence), name="recurrence"),
        # An end time needs a start time and must come after it (same day, no events across midnight).
        CheckConstraint(
            "end_time IS NULL OR (start_time IS NOT NULL AND end_time > start_time)",
            name="end_time_after_start_time",
        ),
        CheckConstraint(
            "repeat_until IS NULL OR (recurrence <> 'none' AND repeat_until >= starts_on)",
            name="repeat_until_matches_recurrence",
        ),
        # Also serves filters on user_id alone, so no separate index on it.
        Index("ix_events_user_id_starts_on", "user_id", "starts_on"),
    )
