import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import ColumnElement, case, func, select
from sqlalchemy.orm import Session

from app.models import Task, TaskPriority, TaskSort, TaskStatus
from app.repositories.errors import flush
from app.repositories.search import LIKE_ESCAPE, escape_like

# Priority sorts by weight, not alphabetically ("high" < "low" < "medium" would be wrong).
PRIORITY_WEIGHT = {TaskPriority.LOW: 1, TaskPriority.MEDIUM: 2, TaskPriority.HIGH: 3}


@dataclass(frozen=True)
class TaskFilters:
    """Resolved list filters. Empty sequences and None mean "no filter"."""

    statuses: Sequence[str] = ()
    priorities: Sequence[str] = ()
    due_from: date | None = None
    due_to: date | None = None
    # When set: due_date < overdue_before and not done. The service passes "today" in the app timezone.
    overdue_before: date | None = None
    # Only tasks that are not done (todo or doing).
    open_only: bool = False
    # Plain text, matched literally (case-insensitive) in title or description.
    search: str | None = None


def open_condition() -> ColumnElement[bool]:
    """Not done yet (todo or doing)."""
    return Task.status != TaskStatus.DONE.value


def _conditions(user_id: uuid.UUID, filters: TaskFilters) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [Task.user_id == user_id]
    if filters.statuses:
        conditions.append(Task.status.in_(filters.statuses))
    if filters.priorities:
        conditions.append(Task.priority.in_(filters.priorities))
    if filters.due_from is not None:
        conditions.append(Task.due_date >= filters.due_from)
    if filters.due_to is not None:
        conditions.append(Task.due_date <= filters.due_to)
    if filters.overdue_before is not None:
        conditions.append(Task.due_date < filters.overdue_before)
    if filters.open_only or filters.overdue_before is not None:
        conditions.append(open_condition())
    if filters.search is not None:
        pattern = f"%{escape_like(filters.search)}%"
        conditions.append(
            Task.title.ilike(pattern, escape=LIKE_ESCAPE)
            | Task.description.ilike(pattern, escape=LIKE_ESCAPE)
        )
    return conditions


def _order_by(sort: str) -> list[ColumnElement]:
    priority_weight = case({p.value: w for p, w in PRIORITY_WEIGHT.items()}, value=Task.priority)
    primary = {
        TaskSort.DUE_DATE: Task.due_date.asc().nulls_last(),
        TaskSort.DUE_DATE_DESC: Task.due_date.desc().nulls_last(),
        TaskSort.PRIORITY: priority_weight.asc(),
        TaskSort.PRIORITY_DESC: priority_weight.desc(),
        TaskSort.CREATED_AT: Task.created_at.asc(),
        TaskSort.CREATED_AT_DESC: Task.created_at.desc(),
    }[TaskSort(sort)]
    # `id` is unique, so the order is total and pages never repeat or skip rows.
    return [primary, Task.id.asc()]


def get_for_user(
    db: Session, user_id: uuid.UUID, task_id: uuid.UUID, *, for_update: bool = False
) -> Task | None:
    """The task if it belongs to the user.

    `for_update=True` is for read-modify-write (update, delete): it takes a row lock (SELECT ... FOR
    UPDATE), so a concurrent writer waits for this transaction, and it overwrites any copy already in
    the session (populate_existing), so the caller decides on the latest committed row, never on a
    stale one. A row deleted meanwhile comes back as None.
    """
    stmt = select(Task).where(Task.id == task_id, Task.user_id == user_id)
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return db.scalar(stmt)


def exists_for_user(db: Session, user_id: uuid.UUID, task_id: uuid.UUID) -> bool:
    """Whether the task belongs to the user, holding a FOR KEY SHARE lock until commit.

    For attachments (`files`): the lock makes a concurrent delete of the task wait for the upload's
    commit (and then remove its files too), or the delete commits first and this returns False.
    """
    stmt = (
        select(Task.id)
        .where(Task.id == task_id, Task.user_id == user_id)
        .with_for_update(read=True, key_share=True)  # FOR KEY SHARE (key_share alone is NO KEY UPDATE)
    )
    return db.scalar(stmt) is not None


def list_for_user(
    db: Session, user_id: uuid.UUID, filters: TaskFilters, sort: str, limit: int, offset: int
) -> tuple[list[Task], int]:
    """One page of the user's tasks plus the total number of matches (same filters, no paging)."""
    conditions = _conditions(user_id, filters)
    total = count_for_user(db, user_id, filters)
    items = db.scalars(
        select(Task).where(*conditions).order_by(*_order_by(sort)).limit(limit).offset(offset)
    ).all()
    return list(items), total


def count_for_user(db: Session, user_id: uuid.UUID, filters: TaskFilters) -> int:
    """How many of the user's tasks match the filters."""
    return db.scalar(select(func.count()).select_from(Task).where(*_conditions(user_id, filters))) or 0


def add(db: Session, task: Task) -> Task:
    """Insert and flush. Raises DuplicateError for unique violations; the caller rolls back."""
    db.add(task)
    flush(db)
    return task


def save(db: Session) -> None:
    """Flush pending changes of loaded tasks. Raises DuplicateError for unique violations."""
    flush(db)


def delete(db: Session, task: Task) -> None:
    db.delete(task)
    flush(db)
