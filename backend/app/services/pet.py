import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import Settings
from app.core.errors import NotFoundError, ValidationError
from app.core.pet_care import is_overdue
from app.models import Pet, PetEvent
from app.repositories import pet as pet_repo
from app.repositories.pet import PetEventFilters, PetFilters
from app.schemas.pet import PetCreate, PetEventCreate, PetEventQuery, PetEventUpdate, PetQuery, PetUpdate


class PetNotFound(NotFoundError):
    detail = "Pet não encontrado."


class PetEventNotFound(NotFoundError):
    detail = "Evento não encontrado."


class FutureBirthDate(ValidationError):
    detail = "A data de nascimento não pode ser no futuro."


class FutureEventDate(ValidationError):
    detail = "A data do evento não pode ser no futuro."


class NextDueBeforeEvent(ValidationError):
    detail = "A próxima data não pode ser anterior à data do evento."


@dataclass(frozen=True)
class PetReminder:
    event: PetEvent
    pet_name: str
    overdue: bool


def _today(settings: Settings) -> date:
    return clock.today(settings.timezone)


def _check_birth_date(birth_date: date | None, today: date) -> None:
    if birth_date is not None and birth_date > today:
        raise FutureBirthDate


def _check_event_dates(occurred_on: date, next_due_on: date | None, today: date) -> None:
    """Mirrors the next_due_after_occurred CHECK (so it is a 422, never a 500) plus "not in the future"."""
    if occurred_on > today:
        raise FutureEventDate
    if next_due_on is not None and next_due_on < occurred_on:
        raise NextDueBeforeEvent


def _changes(row: Pet | PetEvent, requested: dict) -> dict:
    return {field: value for field, value in requested.items() if getattr(row, field) != value}


# --- pets ------------------------------------------------------------------------------------------


def list_pets(db: Session, user_id: uuid.UUID, query: PetQuery) -> tuple[list[Pet], int]:
    filters = PetFilters(species=query.species, search=query.q)
    return pet_repo.list_for_user(db, user_id, filters, query.sort, query.limit, query.offset)


def list_species(db: Session, user_id: uuid.UUID) -> list[str]:
    return pet_repo.distinct_species(db, user_id)


def get_pet(
    db: Session,
    user_id: uuid.UUID,
    pet_id: uuid.UUID,
    *,
    for_update: bool = False,
    no_key_update: bool = False,
) -> Pet:
    """The user's pet. Someone else's pet is reported as missing (404), never as forbidden."""
    pet = pet_repo.get_for_user(db, user_id, pet_id, for_update=for_update, no_key_update=no_key_update)
    if pet is None:
        raise PetNotFound
    return pet


def create_pet(db: Session, settings: Settings, user_id: uuid.UUID, data: PetCreate) -> Pet:
    _check_birth_date(data.birth_date, _today(settings))
    pet = Pet(user_id=user_id, **data.model_dump())
    pet_repo.add(db, pet)
    db.commit()
    return pet


def update_pet(
    db: Session, settings: Settings, user_id: uuid.UUID, pet_id: uuid.UUID, data: PetUpdate
) -> Pet:
    # FOR NO KEY UPDATE: waits for other PATCHes and for a DELETE, but lets event writes (FOR KEY SHARE
    # on the pet) go on while the pet is being edited.
    pet = get_pet(db, user_id, pet_id, for_update=True, no_key_update=True)
    changes = _changes(pet, data.model_dump(exclude_unset=True))
    if "birth_date" in changes:
        try:
            _check_birth_date(changes["birth_date"], _today(settings))
        except FutureBirthDate:
            db.rollback()  # release the row lock now
            raise
    if changes:
        for field, value in changes.items():
            setattr(pet, field, value)
        pet_repo.save(db)
    # Without changes this only ends the transaction (no UPDATE, updated_at untouched) and releases
    # the row lock now, not after the response has been sent.
    db.commit()
    return pet


def delete_pet(db: Session, user_id: uuid.UUID, pet_id: uuid.UUID) -> None:
    """Delete the pet and its events; its expenses stay in finances, without the pet."""
    # Attachments (files with entity_type pet/pet_event) have no FK: the Arquivos module will delete
    # them here (see docs/ROADMAP.md).
    pet = get_pet(db, user_id, pet_id, for_update=True)
    pet_repo.delete(db, pet)
    db.commit()


# --- events ----------------------------------------------------------------------------------------


def _lock_pet(db: Session, user_id: uuid.UUID, pet_id: uuid.UUID) -> None:
    """Check the pet is the user's and keep it from being deleted until commit (FOR KEY SHARE)."""
    if not pet_repo.exists_for_user(db, user_id, pet_id):
        db.rollback()
        raise PetNotFound


def _get_event_for_update(
    db: Session, user_id: uuid.UUID, pet_id: uuid.UUID, event_id: uuid.UUID
) -> PetEvent:
    _lock_pet(db, user_id, pet_id)
    event = pet_repo.get_event_for_user(db, user_id, pet_id, event_id, for_update=True)
    if event is None:
        db.rollback()
        raise PetEventNotFound
    return event


def list_events(
    db: Session, user_id: uuid.UUID, pet_id: uuid.UUID, query: PetEventQuery
) -> tuple[list[PetEvent], int]:
    get_pet(db, user_id, pet_id)
    filters = PetEventFilters(types=query.type, date_from=query.date_from, date_to=query.date_to)
    return pet_repo.list_events(db, pet_id, filters, query.limit, query.offset)


def create_event(
    db: Session, settings: Settings, user_id: uuid.UUID, pet_id: uuid.UUID, data: PetEventCreate
) -> PetEvent:
    _check_event_dates(data.occurred_on, data.next_due_on, _today(settings))
    _lock_pet(db, user_id, pet_id)
    # user_id always comes from the authenticated user; the composite FK ties it to the pet owner.
    event = PetEvent(pet_id=pet_id, user_id=user_id, **data.model_dump())
    pet_repo.add_event(db, event)
    db.commit()
    return event


def update_event(
    db: Session,
    settings: Settings,
    user_id: uuid.UUID,
    pet_id: uuid.UUID,
    event_id: uuid.UUID,
    data: PetEventUpdate,
) -> PetEvent:
    """Partial update. The dates are checked on the combined state (stored row + changes), so moving
    only `occurred_on` past the stored `next_due_on` is a 422 too."""
    event = _get_event_for_update(db, user_id, pet_id, event_id)
    requested = data.model_dump(exclude_unset=True)
    try:
        _check_event_dates(
            requested.get("occurred_on", event.occurred_on),
            requested.get("next_due_on", event.next_due_on),
            _today(settings),
        )
    except ValidationError:
        db.rollback()
        raise
    changes = _changes(event, requested)
    if changes:
        for field, value in changes.items():
            setattr(event, field, value)
        pet_repo.save(db)
    db.commit()
    return event


def delete_event(db: Session, user_id: uuid.UUID, pet_id: uuid.UUID, event_id: uuid.UUID) -> None:
    # Attachments (files with entity_type pet_event) have no FK: the Arquivos module will delete them
    # here (see docs/ROADMAP.md).
    event = _get_event_for_update(db, user_id, pet_id, event_id)
    pet_repo.delete_event(db, event)
    db.commit()


# --- reminders -------------------------------------------------------------------------------------


def list_reminders(db: Session, settings: Settings, user_id: uuid.UUID, within: int) -> list[PetReminder]:
    """Latest event of each series with a next date up to today + `within` days (overdue included).

    The series rule lives in `app.core.pet_care`; the repository runs its SQL twin.
    """
    today = _today(settings)
    return [
        PetReminder(event, pet_name, is_overdue(event.next_due_on, today))
        for event, pet_name in pet_repo.list_reminders(db, user_id, today + timedelta(days=within))
    ]
