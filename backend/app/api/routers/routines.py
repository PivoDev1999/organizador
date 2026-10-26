import uuid
from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from app.api.deps import CurrentUser, SettingsDep, StorageDep
from app.core.database import DbSession
from app.schemas.common import IsoDate, Page
from app.schemas.routine import (
    RoutineCreate,
    RoutineLogCreate,
    RoutineLogQuery,
    RoutineLogRead,
    RoutineQuery,
    RoutineRead,
    RoutineTodayRead,
    RoutineUpdate,
)
from app.services import routine as routine_service

router = APIRouter(prefix="/routines", tags=["routines"])


@router.get("")
def list_routines(
    query: Annotated[RoutineQuery, Query()], db: DbSession, current_user: CurrentUser
) -> Page[RoutineRead]:
    return Page[RoutineRead].of(*routine_service.list_routines(db, current_user.id, query), query)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_routine(data: RoutineCreate, db: DbSession, current_user: CurrentUser) -> RoutineRead:
    return RoutineRead.model_validate(routine_service.create_routine(db, current_user.id, data))


# Declared before "/{routine_id}" so "today" is never parsed as a routine id.
@router.get("/today")
def list_due_today(db: DbSession, settings: SettingsDep, current_user: CurrentUser) -> list[RoutineTodayRead]:
    """Rotinas ativas previstas para hoje (fuso do servidor), cada uma com `done_today`."""
    return [
        RoutineTodayRead.of(item.routine, item.done_today)
        for item in routine_service.list_due_today(db, settings, current_user.id)
    ]


@router.get("/{routine_id}")
def get_routine(routine_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> RoutineRead:
    return RoutineRead.model_validate(routine_service.get_routine(db, current_user.id, routine_id))


@router.patch("/{routine_id}")
def update_routine(
    routine_id: uuid.UUID, data: RoutineUpdate, db: DbSession, current_user: CurrentUser
) -> RoutineRead:
    return RoutineRead.model_validate(routine_service.update_routine(db, current_user.id, routine_id, data))


@router.delete("/{routine_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_routine(
    routine_id: uuid.UUID, db: DbSession, storage: StorageDep, current_user: CurrentUser
) -> None:
    routine_service.delete_routine(db, storage, current_user.id, routine_id)


@router.get("/{routine_id}/logs")
def list_logs(
    routine_id: uuid.UUID,
    query: Annotated[RoutineLogQuery, Query()],
    db: DbSession,
    current_user: CurrentUser,
) -> Page[RoutineLogRead]:
    return Page[RoutineLogRead].of(*routine_service.list_logs(db, current_user.id, routine_id, query), query)


@router.post("/{routine_id}/logs", status_code=status.HTTP_201_CREATED)
def log_done(
    routine_id: uuid.UUID,
    db: DbSession,
    settings: SettingsDep,
    current_user: CurrentUser,
    data: RoutineLogCreate | None = None,
) -> RoutineLogRead:
    """Marca a rotina como feita. Sem corpo (ou sem `done_on`), vale hoje no fuso do servidor."""
    log = routine_service.log_done(db, settings, current_user.id, routine_id, data or RoutineLogCreate())
    return RoutineLogRead.model_validate(log)


@router.delete("/{routine_id}/logs/{done_on}", status_code=status.HTTP_204_NO_CONTENT)
def undo_log(
    routine_id: uuid.UUID,
    done_on: Annotated[IsoDate, Path(description="Dia da marcação (AAAA-MM-DD).")],
    db: DbSession,
    current_user: CurrentUser,
) -> None:
    routine_service.undo_log(db, current_user.id, routine_id, done_on)
