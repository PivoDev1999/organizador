import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, StorageDep
from app.core.database import DbSession
from app.schemas.event import EventCreate, EventOccurrenceRead, EventQuery, EventRead, EventUpdate
from app.services import event as event_service

router = APIRouter(prefix="/events", tags=["events"])


@router.get("")
def list_events(
    query: Annotated[EventQuery, Query()], db: DbSession, current_user: CurrentUser
) -> list[EventOccurrenceRead]:
    """Ocorrências dos eventos entre `from` e `to` (inclusive, até 366 dias), sem paginação.

    Um evento que se repete aparece uma vez por dia em que acontece. Ordem: data, eventos de dia inteiro
    primeiro, depois horário de início, título e id.
    """
    return [EventOccurrenceRead.of(item) for item in event_service.list_events(db, current_user.id, query)]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_event(data: EventCreate, db: DbSession, current_user: CurrentUser) -> EventRead:
    return EventRead.model_validate(event_service.create_event(db, current_user.id, data))


@router.get("/{event_id}")
def get_event(event_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> EventRead:
    return EventRead.model_validate(event_service.get_event(db, current_user.id, event_id))


@router.patch("/{event_id}")
def update_event(
    event_id: uuid.UUID, data: EventUpdate, db: DbSession, current_user: CurrentUser
) -> EventRead:
    return EventRead.model_validate(event_service.update_event(db, current_user.id, event_id, data))


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(event_id: uuid.UUID, db: DbSession, storage: StorageDep, current_user: CurrentUser) -> None:
    event_service.delete_event(db, storage, current_user.id, event_id)
