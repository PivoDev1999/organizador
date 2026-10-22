import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, EntityMixin, in_check


class TaskStatus(StrEnum):
    TODO = "todo"
    DOING = "doing"
    DONE = "done"


class TaskPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TaskSort(StrEnum):
    """Accepted list orderings; a leading "-" means descending."""

    DUE_DATE = "due_date"
    DUE_DATE_DESC = "-due_date"
    PRIORITY = "priority"
    PRIORITY_DESC = "-priority"
    CREATED_AT = "created_at"
    CREATED_AT_DESC = "-created_at"


class Task(EntityMixin, Base):
    __tablename__ = "tasks"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), server_default=TaskStatus.TODO.value)
    priority: Mapped[str] = mapped_column(String(10), server_default=TaskPriority.MEDIUM.value)
    due_date: Mapped[date | None]
    completed_at: Mapped[datetime | None]

    __table_args__ = (
        CheckConstraint(in_check("status", TaskStatus), name="status"),
        CheckConstraint(in_check("priority", TaskPriority), name="priority"),
        CheckConstraint("(status = 'done') = (completed_at IS NOT NULL)", name="completed_at_matches_status"),
        Index("ix_tasks_user_id_status", "user_id", "status"),
        Index("ix_tasks_user_id_due_date", "user_id", "due_date"),
    )
