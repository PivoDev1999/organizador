import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import ColumnElement, exists, func, select
from sqlalchemy.orm import Session

from app.models import Routine, RoutineLog, RoutineSort
from app.repositories.errors import flush
from app.repositories.search import LIKE_ESCAPE, TEXT_SORT_COLLATION, escape_like

# Name of the UNIQUE (routine_id, done_on) constraint, from the naming convention ("uq").
LOG_UNIQUE_CONSTRAINT = "uq_routine_logs_routine_id_done_on"


@dataclass(frozen=True)
class RoutineFilters:
    """Resolved list filters. Empty sequences and None mean "no filter"."""

    frequencies: Sequence[str] = ()
    is_active: bool | None = None
    # Plain text, matched literally (case-insensitive) in the name.
    search: str | None = None


def _conditions(user_id: uuid.UUID, filters: RoutineFilters) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [Routine.user_id == user_id]
    if filters.frequencies:
        conditions.append(Routine.frequency.in_(filters.frequencies))
    if filters.is_active is not None:
        conditions.append(Routine.is_active.is_(filters.is_active))
    if filters.search is not None:
        conditions.append(Routine.name.ilike(f"%{escape_like(filters.search)}%", escape=LIKE_ESCAPE))
    return conditions


def _sortable_name() -> ColumnElement[str]:
    return Routine.name.collate(TEXT_SORT_COLLATION)


def _order_by(sort: str) -> list[ColumnElement]:
    primary = {
        RoutineSort.NAME: _sortable_name().asc(),
        RoutineSort.NAME_DESC: _sortable_name().desc(),
        RoutineSort.CREATED_AT: Routine.created_at.asc(),
        RoutineSort.CREATED_AT_DESC: Routine.created_at.desc(),
    }[RoutineSort(sort)]
    # `id` is unique, so the order is total and pages never repeat or skip rows.
    return [primary, Routine.id.asc()]


def get_for_user(
    db: Session, user_id: uuid.UUID, routine_id: uuid.UUID, *, for_update: bool = False
) -> Routine | None:
    """The routine if it belongs to the user.

    `for_update=True` locks the row (SELECT ... FOR UPDATE) and refreshes any copy already in the
    session, so read-modify-write decides on the latest committed row. See `task.get_for_user`.
    """
    stmt = select(Routine).where(Routine.id == routine_id, Routine.user_id == user_id)
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return db.scalar(stmt)


def list_for_user(
    db: Session, user_id: uuid.UUID, filters: RoutineFilters, sort: str, limit: int, offset: int
) -> tuple[list[Routine], int]:
    """One page of the user's routines plus the total number of matches (same filters, no paging)."""
    conditions = _conditions(user_id, filters)
    total = db.scalar(select(func.count()).select_from(Routine).where(*conditions)) or 0
    items = db.scalars(
        select(Routine).where(*conditions).order_by(*_order_by(sort)).limit(limit).offset(offset)
    ).all()
    return list(items), total


def list_active_with_done_flag(db: Session, user_id: uuid.UUID, day: date) -> list[tuple[Routine, bool]]:
    """Every active routine of the user, each with "has a log on `day`", in one query.

    Ordered by time of day (routines without time last), then name and id.
    """
    done = (
        exists()
        .where(RoutineLog.routine_id == Routine.id, RoutineLog.done_on == day)
        .correlate(Routine)
        .label("done")
    )
    rows = db.execute(
        select(Routine, done)
        .where(Routine.user_id == user_id, Routine.is_active.is_(True))
        .order_by(Routine.time_of_day.asc().nulls_last(), _sortable_name().asc(), Routine.id.asc())
    ).all()
    return [(routine, bool(is_done)) for routine, is_done in rows]


def add(db: Session, routine: Routine) -> Routine:
    """Insert and flush. The caller rolls back after an error."""
    db.add(routine)
    flush(db)
    return routine


def save(db: Session) -> None:
    """Flush pending changes of loaded routines."""
    flush(db)


def delete(db: Session, routine: Routine) -> None:
    """Delete the routine; its logs go with it (ON DELETE CASCADE, passive_deletes)."""
    db.delete(routine)
    flush(db)


def get_log(
    db: Session, routine_id: uuid.UUID, done_on: date, *, for_update: bool = False
) -> RoutineLog | None:
    stmt = select(RoutineLog).where(RoutineLog.routine_id == routine_id, RoutineLog.done_on == done_on)
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return db.scalar(stmt)


def list_logs(
    db: Session,
    routine_id: uuid.UUID,
    date_from: date | None,
    date_to: date | None,
    limit: int,
    offset: int,
) -> tuple[list[RoutineLog], int]:
    """One page of the routine's logs, newest first, plus the total of matches."""
    conditions: list[ColumnElement[bool]] = [RoutineLog.routine_id == routine_id]
    if date_from is not None:
        conditions.append(RoutineLog.done_on >= date_from)
    if date_to is not None:
        conditions.append(RoutineLog.done_on <= date_to)
    total = db.scalar(select(func.count()).select_from(RoutineLog).where(*conditions)) or 0
    # done_on is unique per routine, so the order is already total.
    items = db.scalars(
        select(RoutineLog).where(*conditions).order_by(RoutineLog.done_on.desc()).limit(limit).offset(offset)
    ).all()
    return list(items), total


def add_log(db: Session, log: RoutineLog) -> RoutineLog:
    """Insert and flush. Raises DuplicateError (LOG_UNIQUE_CONSTRAINT) if the day is already logged."""
    db.add(log)
    flush(db)
    return log


def delete_log(db: Session, log: RoutineLog) -> None:
    db.delete(log)
    flush(db)
