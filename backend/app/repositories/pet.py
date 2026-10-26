import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session, aliased

from app.models import Pet, PetEvent, PetSort
from app.repositories.errors import flush
from app.repositories.search import LIKE_ESCAPE, TEXT_SORT_COLLATION, escape_like


@dataclass(frozen=True)
class PetFilters:
    """Resolved list filters. Empty sequences and None mean "no filter"."""

    species: Sequence[str] = ()
    # Plain text, matched literally (case-insensitive) in the name.
    search: str | None = None


@dataclass(frozen=True)
class PetEventFilters:
    types: Sequence[str] = ()
    # Inclusive bounds on occurred_on.
    date_from: date | None = None
    date_to: date | None = None


def _sortable_name() -> ColumnElement[str]:
    return Pet.name.collate(TEXT_SORT_COLLATION)


def _order_by(sort: str) -> list[ColumnElement]:
    primary = {
        PetSort.NAME: _sortable_name().asc(),
        PetSort.NAME_DESC: _sortable_name().desc(),
        PetSort.CREATED_AT: Pet.created_at.asc(),
        PetSort.CREATED_AT_DESC: Pet.created_at.desc(),
    }[PetSort(sort)]
    # `id` is unique, so the order is total and pages never repeat or skip rows.
    return [primary, Pet.id.asc()]


def _pet_conditions(user_id: uuid.UUID, filters: PetFilters) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [Pet.user_id == user_id]
    if filters.species:
        conditions.append(Pet.species.in_(filters.species))
    if filters.search is not None:
        conditions.append(Pet.name.ilike(f"%{escape_like(filters.search)}%", escape=LIKE_ESCAPE))
    return conditions


# --- pets ------------------------------------------------------------------------------------------


def get_for_user(
    db: Session,
    user_id: uuid.UUID,
    pet_id: uuid.UUID,
    *,
    for_update: bool = False,
    no_key_update: bool = False,
) -> Pet | None:
    """The pet if it belongs to the user.

    `for_update=True` locks the row and refreshes any copy already in the session, so read-modify-write
    decides on the latest committed row (see `task.get_for_user`). The lock is FOR UPDATE (deletes), or
    FOR NO KEY UPDATE with `no_key_update=True` (plain updates): that one still serializes with other
    updates and with a delete, but not with the FOR KEY SHARE that event writes take (`exists_for_user`),
    so renaming a pet does not hold up its events.
    """
    stmt = select(Pet).where(Pet.id == pet_id, Pet.user_id == user_id)
    if for_update:
        # key_share=True alone renders FOR NO KEY UPDATE.
        stmt = stmt.with_for_update(key_share=no_key_update).execution_options(populate_existing=True)
    return db.scalar(stmt)


def exists_for_user(db: Session, user_id: uuid.UUID, pet_id: uuid.UUID) -> bool:
    """Whether the pet belongs to the user, holding a FOR KEY SHARE lock until commit.

    For writes of its events: the lock blocks a concurrent delete of the pet (which would otherwise make
    the event insert fail on the foreign key, or update a row the cascade is removing). A delete that
    committed first makes this return False (404). Plain updates of the pet (FOR NO KEY UPDATE) are not
    blocked.
    """
    stmt = (
        select(Pet.id)
        .where(Pet.id == pet_id, Pet.user_id == user_id)
        .with_for_update(read=True, key_share=True)  # FOR KEY SHARE (key_share alone is NO KEY UPDATE)
    )
    return db.scalar(stmt) is not None


def list_for_user(
    db: Session, user_id: uuid.UUID, filters: PetFilters, sort: str, limit: int, offset: int
) -> tuple[list[Pet], int]:
    """One page of the user's pets plus the total number of matches (same filters, no paging)."""
    conditions = _pet_conditions(user_id, filters)
    total = db.scalar(select(func.count()).select_from(Pet).where(*conditions)) or 0
    items = db.scalars(
        select(Pet).where(*conditions).order_by(*_order_by(sort)).limit(limit).offset(offset)
    ).all()
    return list(items), total


def distinct_species(db: Session, user_id: uuid.UUID) -> list[str]:
    """Distinct species among the user's pets, sorted (pt-BR)."""
    # GROUP BY rather than DISTINCT: Postgres requires DISTINCT's ORDER BY expressions (here with
    # COLLATE) to appear in the select list.
    return list(
        db.scalars(
            select(Pet.species)
            .where(Pet.user_id == user_id)
            .group_by(Pet.species)
            .order_by(Pet.species.collate(TEXT_SORT_COLLATION))
        ).all()
    )


def add(db: Session, pet: Pet) -> Pet:
    """Insert and flush. The caller rolls back after an error."""
    db.add(pet)
    flush(db)
    return pet


def save(db: Session) -> None:
    """Flush pending changes of loaded pets and events."""
    flush(db)


def delete(db: Session, pet: Pet) -> None:
    """Delete the pet. Its events go with it (ON DELETE CASCADE); its expenses stay, with pet_id set to
    NULL by the database (ON DELETE SET NULL (pet_id)). Both relationships are passive_deletes."""
    db.delete(pet)
    flush(db)


# --- events ----------------------------------------------------------------------------------------


def get_event_for_user(
    db: Session, user_id: uuid.UUID, pet_id: uuid.UUID, event_id: uuid.UUID, *, for_update: bool = False
) -> PetEvent | None:
    """The event if it belongs to that pet of the user (an event of another pet is None)."""
    stmt = select(PetEvent).where(
        PetEvent.id == event_id, PetEvent.pet_id == pet_id, PetEvent.user_id == user_id
    )
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return db.scalar(stmt)


def list_events(
    db: Session, pet_id: uuid.UUID, filters: PetEventFilters, limit: int, offset: int
) -> tuple[list[PetEvent], int]:
    """One page of the pet's events, newest first, plus the total of matches."""
    conditions: list[ColumnElement[bool]] = [PetEvent.pet_id == pet_id]
    if filters.types:
        conditions.append(PetEvent.type.in_(filters.types))
    if filters.date_from is not None:
        conditions.append(PetEvent.occurred_on >= filters.date_from)
    if filters.date_to is not None:
        conditions.append(PetEvent.occurred_on <= filters.date_to)
    total = db.scalar(select(func.count()).select_from(PetEvent).where(*conditions)) or 0
    items = db.scalars(
        select(PetEvent)
        .where(*conditions)
        .order_by(PetEvent.occurred_on.desc(), PetEvent.created_at.desc(), PetEvent.id.asc())
        .limit(limit)
        .offset(offset)
    ).all()
    return list(items), total


def add_event(db: Session, event: PetEvent) -> PetEvent:
    db.add(event)
    flush(db)
    return event


def delete_event(db: Session, event: PetEvent) -> None:
    db.delete(event)
    flush(db)


# --- reminders (SQL twin of app.core.pet_care.active_reminders; tests check that both agree) -------


def series_description() -> ColumnElement[str | None]:
    """SQL twin of `pet_care.normalize_description`: btrim trims spaces only, like strip(" "), and ICU's
    lower case matches Python's str.lower() (the default musl collation does not)."""
    return func.lower(func.btrim(PetEvent.description).collate(TEXT_SORT_COLLATION))


def list_reminders(db: Session, user_id: uuid.UUID, last_day: date) -> list[tuple[PetEvent, str]]:
    """The user's reminders due up to `last_day` (overdue ones included), each with the pet name.

    DISTINCT ON keeps the newest event of each (pet, type, normalized description) series (NULL
    descriptions form one series: DISTINCT ON treats NULLs as equal); only then the due-date filter
    applies, so an older event of a series never resurfaces. Ordered by due date, pet name (pt-BR), id.
    """
    latest = (
        select(PetEvent)
        .where(PetEvent.user_id == user_id)
        .ext(distinct_on(PetEvent.pet_id, PetEvent.type, series_description()))
        .order_by(
            PetEvent.pet_id,
            PetEvent.type,
            series_description(),
            PetEvent.occurred_on.desc(),
            PetEvent.created_at.desc(),
            PetEvent.id.desc(),
        )
        .subquery()
    )
    event = aliased(PetEvent, latest)
    rows = db.execute(
        select(event, Pet.name)
        .join(Pet, (Pet.id == event.pet_id) & (Pet.user_id == event.user_id))
        .where(event.next_due_on.is_not(None), event.next_due_on <= last_day)
        .order_by(event.next_due_on.asc(), _sortable_name().asc(), event.id.asc())
    ).all()
    return [(row[0], row[1]) for row in rows]
