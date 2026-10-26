import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, SettingsDep
from app.core.database import DbSession
from app.schemas.common import Page
from app.schemas.pet import (
    PetCreate,
    PetEventCreate,
    PetEventQuery,
    PetEventRead,
    PetEventUpdate,
    PetQuery,
    PetRead,
    PetReminderQuery,
    PetReminderRead,
    PetUpdate,
)
from app.services import pet as pet_service

router = APIRouter(prefix="/pets", tags=["pets"])


@router.get("")
def list_pets(query: Annotated[PetQuery, Query()], db: DbSession, current_user: CurrentUser) -> Page[PetRead]:
    return Page[PetRead].of(*pet_service.list_pets(db, current_user.id, query), query)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_pet(data: PetCreate, db: DbSession, settings: SettingsDep, current_user: CurrentUser) -> PetRead:
    return PetRead.model_validate(pet_service.create_pet(db, settings, current_user.id, data))


# Fixed paths are declared before "/{pet_id}" so they are never parsed as a pet id.
@router.get("/species")
def list_species(db: DbSession, current_user: CurrentUser) -> list[str]:
    """Espécies já usadas pelo usuário, em ordem alfabética."""
    return pet_service.list_species(db, current_user.id)


@router.get("/reminders")
def list_reminders(
    query: Annotated[PetReminderQuery, Query()],
    db: DbSession,
    settings: SettingsDep,
    current_user: CurrentUser,
) -> list[PetReminderRead]:
    """Próximas datas até hoje + `within` dias (atrasadas incluídas), por data, nome do pet e id.

    Só o evento mais recente de cada série (pet, tipo e descrição, sem diferenciar maiúsculas nem
    espaços nas pontas) gera lembrete: registrar o reforço resolve o lembrete anterior.
    """
    reminders = pet_service.list_reminders(db, settings, current_user.id, query.within)
    return [PetReminderRead.of(reminder) for reminder in reminders]


@router.get("/{pet_id}")
def get_pet(pet_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> PetRead:
    return PetRead.model_validate(pet_service.get_pet(db, current_user.id, pet_id))


@router.patch("/{pet_id}")
def update_pet(
    pet_id: uuid.UUID, data: PetUpdate, db: DbSession, settings: SettingsDep, current_user: CurrentUser
) -> PetRead:
    return PetRead.model_validate(pet_service.update_pet(db, settings, current_user.id, pet_id, data))


@router.delete("/{pet_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pet(pet_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> None:
    """Apaga o pet e seus eventos. Os gastos ligados a ele continuam nas finanças, sem o pet."""
    pet_service.delete_pet(db, current_user.id, pet_id)


@router.get("/{pet_id}/events")
def list_events(
    pet_id: uuid.UUID, query: Annotated[PetEventQuery, Query()], db: DbSession, current_user: CurrentUser
) -> Page[PetEventRead]:
    return Page[PetEventRead].of(*pet_service.list_events(db, current_user.id, pet_id, query), query)


@router.post("/{pet_id}/events", status_code=status.HTTP_201_CREATED)
def create_event(
    pet_id: uuid.UUID, data: PetEventCreate, db: DbSession, settings: SettingsDep, current_user: CurrentUser
) -> PetEventRead:
    return PetEventRead.model_validate(pet_service.create_event(db, settings, current_user.id, pet_id, data))


@router.patch("/{pet_id}/events/{event_id}")
def update_event(
    pet_id: uuid.UUID,
    event_id: uuid.UUID,
    data: PetEventUpdate,
    db: DbSession,
    settings: SettingsDep,
    current_user: CurrentUser,
) -> PetEventRead:
    event = pet_service.update_event(db, settings, current_user.id, pet_id, event_id, data)
    return PetEventRead.model_validate(event)


@router.delete("/{pet_id}/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(pet_id: uuid.UUID, event_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> None:
    pet_service.delete_event(db, current_user.id, pet_id, event_id)
