import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import Settings
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.schedule import SCHEDULE_FIELDS, is_due, schedule_problem
from app.core.storage import Storage
from app.models import Routine, RoutineLog
from app.models.file import FileEntityType
from app.repositories import routine as routine_repo
from app.repositories.errors import DuplicateError
from app.repositories.routine import LOG_UNIQUE_CONSTRAINT, RoutineFilters
from app.schemas.routine import RoutineCreate, RoutineLogCreate, RoutineLogQuery, RoutineQuery, RoutineUpdate
from app.services import files as files_service


class RoutineNotFound(NotFoundError):
    detail = "Rotina não encontrada."


class RoutineLogNotFound(NotFoundError):
    detail = "Registro não encontrado."


class RoutineInactive(ConflictError):
    detail = "Rotina inativa."


class RoutineAlreadyDone(ConflictError):
    detail = "Rotina já marcada como feita nesse dia."


class InvalidSchedule(ValidationError):
    detail = "Agenda incompatível com a frequência."


class FutureLogDate(ValidationError):
    detail = "A data não pode ser no futuro."


@dataclass(frozen=True)
class DueRoutine:
    routine: Routine
    done_today: bool


def list_routines(db: Session, user_id: uuid.UUID, query: RoutineQuery) -> tuple[list[Routine], int]:
    filters = RoutineFilters(frequencies=query.frequency, is_active=query.is_active, search=query.q)
    return routine_repo.list_for_user(db, user_id, filters, query.sort, query.limit, query.offset)


def list_due_today(db: Session, settings: Settings, user_id: uuid.UUID) -> list[DueRoutine]:
    """Active routines scheduled for today (app timezone), each with whether it is already done.

    One query loads the user's active routines with a "done today" flag; `is_due` filters them in
    Python. A household has tens of routines, so this costs nothing, and the schedule rule (with the
    "day 31 falls on the last day of the month" case) lives in one pure, tested function instead of
    being duplicated in SQL.
    """
    return list_due_on(db, user_id, clock.today(settings.timezone))


def list_due_on(db: Session, user_id: uuid.UUID, day: date) -> list[DueRoutine]:
    """Active routines scheduled for `day`, each with whether it is done on that day (see above)."""
    return [
        DueRoutine(routine, done)
        for routine, done in routine_repo.list_active_with_done_flag(db, user_id, day)
        if is_due(routine, day)
    ]


def get_routine(
    db: Session, user_id: uuid.UUID, routine_id: uuid.UUID, *, for_update: bool = False
) -> Routine:
    """The user's routine. Someone else's routine is reported as missing (404), never as forbidden."""
    routine = routine_repo.get_for_user(db, user_id, routine_id, for_update=for_update)
    if routine is None:
        raise RoutineNotFound
    return routine


def create_routine(db: Session, user_id: uuid.UUID, data: RoutineCreate) -> Routine:
    # The schema already checked the schedule (no stored state is involved on create).
    routine = Routine(user_id=user_id, **data.model_dump())
    routine_repo.add(db, routine)
    db.commit()
    return routine


def update_routine(db: Session, user_id: uuid.UUID, routine_id: uuid.UUID, data: RoutineUpdate) -> Routine:
    """Apply a partial update, keeping the schedule coherent with the frequency.

    On a frequency change, the fields only the old frequency used are cleared, and the ones the new
    frequency requires must come in the same body. The final check runs on the combined state (stored
    row + changes), so a PATCH can never leave the routine incoherent, with or without a frequency
    change (e.g. a weekly routine with `days_of_week: []`).
    """
    routine = get_routine(db, user_id, routine_id, for_update=True)
    requested = data.model_dump(exclude_unset=True)

    frequency = requested.get("frequency", routine.frequency)
    if frequency != routine.frequency:
        for field in SCHEDULE_FIELDS[routine.frequency]:
            requested.setdefault(field, None)
    problem = schedule_problem(
        frequency,
        requested.get("days_of_week", routine.days_of_week),
        requested.get("day_of_month", routine.day_of_month),
    )
    if problem:
        db.rollback()  # release the row lock now
        raise InvalidSchedule(problem)

    changes = {field: value for field, value in requested.items() if getattr(routine, field) != value}
    if not changes:
        # Nothing to write: end the transaction (no UPDATE, updated_at untouched) and release the lock.
        db.commit()
        return routine
    for field, value in changes.items():
        setattr(routine, field, value)
    routine_repo.save(db)
    db.commit()
    return routine


def delete_routine(db: Session, storage: Storage, user_id: uuid.UUID, routine_id: uuid.UUID) -> None:
    routine = get_routine(db, user_id, routine_id, for_update=True)
    routine_repo.delete(db, routine)
    keys = files_service.delete_attachments(db, user_id, FileEntityType.ROUTINE, [routine_id])
    db.commit()
    files_service.purge_objects(storage, keys)


def list_logs(
    db: Session, user_id: uuid.UUID, routine_id: uuid.UUID, query: RoutineLogQuery
) -> tuple[list[RoutineLog], int]:
    get_routine(db, user_id, routine_id)
    return routine_repo.list_logs(db, routine_id, query.date_from, query.date_to, query.limit, query.offset)


def log_done(
    db: Session, settings: Settings, user_id: uuid.UUID, routine_id: uuid.UUID, data: RoutineLogCreate
) -> RoutineLog:
    """Mark the routine as done on a day (default: today in the app timezone).

    Past days and days outside the schedule are accepted (done late or extra); future days are not.
    The routine row stays locked until commit, so a concurrent PATCH cannot deactivate it between the
    `is_active` check and the insert. The UNIQUE (routine_id, done_on) constraint settles duplicates,
    including two concurrent requests for the same day.
    """
    today = clock.today(settings.timezone)
    done_on = data.done_on or today
    if done_on > today:
        raise FutureLogDate
    routine = get_routine(db, user_id, routine_id, for_update=True)
    if not routine.is_active:
        db.rollback()
        raise RoutineInactive

    # user_id always comes from the authenticated user; the composite FK ties it to the routine owner.
    log = RoutineLog(routine_id=routine.id, user_id=user_id, done_on=done_on, note=data.note)
    try:
        routine_repo.add_log(db, log)
    except DuplicateError as exc:
        db.rollback()
        if exc.constraint == LOG_UNIQUE_CONSTRAINT:
            raise RoutineAlreadyDone from exc
        raise
    db.commit()
    return log


def undo_log(db: Session, user_id: uuid.UUID, routine_id: uuid.UUID, done_on: date) -> None:
    """Remove the mark of that day. Allowed for inactive routines too (fixing a mistake)."""
    routine = get_routine(db, user_id, routine_id)
    log = routine_repo.get_log(db, routine.id, done_on, for_update=True)
    if log is None:
        raise RoutineLogNotFound
    routine_repo.delete_log(db, log)
    db.commit()
