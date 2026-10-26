import uuid
from datetime import date, datetime
from typing import Annotated, Protocol, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from app.models.pet import PetEventType, PetSort
from app.schemas.common import (
    DbText,
    IsoDate,
    NotNull,
    PageQuery,
    decimal_type,
    drop_blanks,
    optional_text,
    required_text,
)

# Column sizes of pets and pet_events (Text columns get an API limit).
NAME_MAX_LENGTH = 100
SPECIES_MAX_LENGTH = 50
BREED_MAX_LENGTH = 100
NOTES_MAX_LENGTH = 5000
DESCRIPTION_MAX_LENGTH = 1000
SEARCH_MAX_LENGTH = 100
REMINDERS_MAX_WITHIN = 365
REMINDERS_DEFAULT_WITHIN = 30

# NUMERIC(5, 2): up to 999.99 kg. Floats are fine here (a weight is not money).
WEIGHT_PLACES, WEIGHT_DIGITS = 2, 5
Weight = decimal_type(WEIGHT_PLACES, WEIGHT_DIGITS, "Peso em kg com até 2 casas, como texto.")

PetName = Annotated[
    DbText,
    AfterValidator(
        required_text(
            NAME_MAX_LENGTH, "Informe o nome.", f"O nome deve ter no máximo {NAME_MAX_LENGTH} caracteres."
        )
    ),
    NotNull,
]
Species = Annotated[
    DbText,
    AfterValidator(
        required_text(
            SPECIES_MAX_LENGTH,
            "Informe a espécie.",
            f"A espécie deve ter no máximo {SPECIES_MAX_LENGTH} caracteres.",
        )
    ),
    NotNull,
]
# Blank (after strip) becomes None.
Breed = Annotated[
    DbText,
    AfterValidator(
        optional_text(BREED_MAX_LENGTH, f"A raça deve ter no máximo {BREED_MAX_LENGTH} caracteres.")
    ),
]
Notes = Annotated[
    DbText,
    AfterValidator(
        optional_text(NOTES_MAX_LENGTH, f"As observações devem ter no máximo {NOTES_MAX_LENGTH} caracteres.")
    ),
]
EventDescription = Annotated[
    DbText,
    AfterValidator(
        optional_text(
            DESCRIPTION_MAX_LENGTH, f"A descrição deve ter no máximo {DESCRIPTION_MAX_LENGTH} caracteres."
        )
    ),
]
SearchText = Annotated[
    DbText,
    AfterValidator(
        optional_text(SEARCH_MAX_LENGTH, f"A busca deve ter no máximo {SEARCH_MAX_LENGTH} caracteres.")
    ),
]
# Query filter compared with the stored (already stripped) species; a blank one means "no filter".
SpeciesFilter = Annotated[
    DbText,
    AfterValidator(
        optional_text(SPECIES_MAX_LENGTH, f"A espécie deve ter no máximo {SPECIES_MAX_LENGTH} caracteres.")
    ),
]
PositiveWeight = Annotated[Weight, Field(gt=0)]
EventType = Annotated[PetEventType, NotNull]
OccurredOn = Annotated[IsoDate, NotNull]

# Unknown fields are rejected (422), not ignored. Enums are stored as their plain string values.
_INPUT_CONFIG = ConfigDict(extra="forbid", use_enum_values=True)


class PetCreate(BaseModel):
    """The birth date must not be in the future: that depends on today, so the service checks it."""

    model_config = _INPUT_CONFIG

    name: PetName
    species: Species = Field(description="Espécie, como Cachorro ou Gato.")
    breed: Breed | None = None
    birth_date: IsoDate | None = Field(
        default=None, description="Data de nascimento; não pode ser no futuro."
    )
    weight_kg: PositiveWeight | None = Field(default=None, description="Peso em kg (maior que 0).")
    notes: Notes | None = None


class PetUpdate(BaseModel):
    """Partial update: only the fields present in the body change (see `model_fields_set`).

    `name` and `species` may be omitted but not sent as null (NotNull, 422). The others accept null to
    clear the value.
    """

    model_config = _INPUT_CONFIG

    name: PetName = None
    species: Species = None
    breed: Breed | None = None
    birth_date: IsoDate | None = None
    weight_kg: PositiveWeight | None = None
    notes: Notes | None = None


class PetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    species: str
    breed: str | None
    birth_date: date | None
    weight_kg: Weight | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class PetEventCreate(BaseModel):
    """Dates are checked by the service: `occurred_on` not in the future (today in the app timezone)
    and `next_due_on` not before `occurred_on` (on the combined state, for a PATCH)."""

    model_config = _INPUT_CONFIG

    type: EventType
    occurred_on: OccurredOn = Field(description="Dia em que aconteceu; não pode ser no futuro.")
    next_due_on: IsoDate | None = Field(
        default=None,
        description="Próxima data prevista (reforço, dose); gera lembrete até o próximo evento da série.",
    )
    description: EventDescription | None = None


class PetEventUpdate(BaseModel):
    """Partial update. `type` and `occurred_on` may be omitted but not sent as null."""

    model_config = _INPUT_CONFIG

    type: EventType = None
    occurred_on: OccurredOn = None
    next_due_on: IsoDate | None = None
    description: EventDescription | None = None


class PetEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pet_id: uuid.UUID
    type: PetEventType
    occurred_on: date
    next_due_on: date | None
    description: str | None
    created_at: datetime
    updated_at: datetime


class ReminderEvent(Protocol):
    """What a reminder needs from an event (the ORM PetEvent fits)."""

    id: uuid.UUID
    pet_id: uuid.UUID
    type: str
    description: str | None
    occurred_on: date
    next_due_on: date | None


class ReminderView(Protocol):
    """A reminder as the service hands it over: the event plus what it computed."""

    event: ReminderEvent
    pet_name: str
    overdue: bool


class PetReminderRead(BaseModel):
    event_id: uuid.UUID
    pet_id: uuid.UUID
    pet_name: str
    type: PetEventType
    description: str | None
    occurred_on: date
    next_due_on: date
    overdue: bool = Field(description="Próxima data anterior a hoje (no fuso do servidor).")

    @classmethod
    def of(cls, reminder: ReminderView) -> Self:
        """Build from the service view: an ORM event plus the pet name and the computed flag."""
        event = reminder.event
        return cls(
            event_id=event.id,
            pet_id=event.pet_id,
            pet_name=reminder.pet_name,
            type=event.type,
            description=event.description,
            occurred_on=event.occurred_on,
            next_due_on=event.next_due_on,
            overdue=reminder.overdue,
        )


class PetQuery(PageQuery):
    """Query string of `GET /api/pets`. Every filter is optional and they combine with AND."""

    species: Annotated[list[SpeciesFilter], AfterValidator(drop_blanks)] = Field(
        default=[], description="Uma ou mais espécies (repita o parâmetro); comparação exata."
    )
    q: SearchText | None = Field(default=None, description="Busca no nome, sem diferenciar maiúsculas.")
    sort: PetSort = Field(default=PetSort.NAME, description="Ordenação; prefixo '-' para decrescente.")


class PetEventQuery(PageQuery):
    """Query string of `GET /api/pets/{id}/events`. Newest first."""

    model_config = ConfigDict(use_enum_values=True)

    type: list[PetEventType] = Field(default=[], description="Um ou mais tipos (repita o parâmetro).")
    date_from: IsoDate | None = Field(
        default=None, alias="from", description="Ocorridos a partir desta data (inclusiva)."
    )
    date_to: IsoDate | None = Field(
        default=None, alias="to", description="Ocorridos até esta data (inclusiva)."
    )

    @model_validator(mode="after")
    def _check_range(self) -> Self:
        if self.date_from is not None and self.date_to is not None and self.date_from > self.date_to:
            raise ValueError("A data inicial (from) não pode ser posterior à data final (to).")
        return self


class PetReminderQuery(BaseModel):
    within: int = Field(
        default=REMINDERS_DEFAULT_WITHIN,
        ge=0,
        le=REMINDERS_MAX_WITHIN,
        description="Janela em dias (0 a 365): próximas datas até hoje + N. Atrasados sempre entram.",
    )
