import datetime
import uuid
from typing import Annotated, Any, Protocol, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from app.core.agenda import RANGE_MAX_DAYS, event_problem, range_problem
from app.models.event import EventRecurrence
from app.schemas.common import DbText, IsoDate, IsoTime, NotNull, optional_text, required_text
from app.schemas.task import DESCRIPTION_MAX_LENGTH

TITLE_MAX_LENGTH = 200  # events.title is VARCHAR(200)
LOCATION_MAX_LENGTH = 200  # events.location is VARCHAR(200)
SEARCH_MAX_LENGTH = 200

EventTitle = Annotated[
    DbText,
    AfterValidator(
        required_text(
            TITLE_MAX_LENGTH,
            "Informe o título.",
            f"O título deve ter no máximo {TITLE_MAX_LENGTH} caracteres.",
        )
    ),
    NotNull,
]
# Blank (after strip) becomes None.
EventDescription = Annotated[
    DbText,
    AfterValidator(
        optional_text(
            DESCRIPTION_MAX_LENGTH, f"A descrição deve ter no máximo {DESCRIPTION_MAX_LENGTH} caracteres."
        )
    ),
]
Location = Annotated[
    DbText,
    AfterValidator(
        optional_text(LOCATION_MAX_LENGTH, f"O local deve ter no máximo {LOCATION_MAX_LENGTH} caracteres.")
    ),
]
SearchText = Annotated[
    DbText,
    AfterValidator(
        optional_text(SEARCH_MAX_LENGTH, f"A busca deve ter no máximo {SEARCH_MAX_LENGTH} caracteres.")
    ),
]
StartsOn = Annotated[IsoDate, NotNull]
Recurrence = Annotated[EventRecurrence, NotNull]

# Unknown fields are rejected (422), not ignored. Enums are stored as their plain string values.
_INPUT_CONFIG = ConfigDict(extra="forbid", use_enum_values=True)

START_TIME_DESCRIPTION = "Horário de início; sem ele, o evento é de dia inteiro."
END_TIME_DESCRIPTION = "Horário de término, no mesmo dia; exige start_time e deve ser depois dele."
RECURRENCE_DESCRIPTION = (
    "Repetição a partir de starts_on: none, weekly (a cada 7 dias), monthly (mesmo dia do mês; em meses "
    "mais curtos, o último dia) ou yearly (29/02 cai em 28/02 nos anos não bissextos)."
)
REPEAT_UNTIL_DESCRIPTION = (
    "Último dia da repetição (inclusive); null repete sem fim. Só para eventos que se repetem, e não "
    "antes de starts_on."
)


class EventCreate(BaseModel):
    model_config = _INPUT_CONFIG

    title: EventTitle
    description: EventDescription | None = None
    location: Location | None = None
    starts_on: StartsOn = Field(description="Dia do evento (o primeiro, se ele se repete).")
    start_time: IsoTime | None = Field(default=None, description=START_TIME_DESCRIPTION)
    end_time: IsoTime | None = Field(default=None, description=END_TIME_DESCRIPTION)
    recurrence: Recurrence = Field(default=EventRecurrence.NONE, description=RECURRENCE_DESCRIPTION)
    repeat_until: IsoDate | None = Field(default=None, description=REPEAT_UNTIL_DESCRIPTION)

    @model_validator(mode="after")
    def _check_combination(self) -> Self:
        problem = event_problem(
            self.starts_on, self.start_time, self.end_time, self.recurrence, self.repeat_until
        )
        if problem:
            raise ValueError(problem)
        return self


class EventUpdate(BaseModel):
    """Partial update: only the fields present in the body change (see `model_fields_set`).

    `title`, `starts_on` and `recurrence` may be omitted but not sent as null (NotNull, 422). The others
    accept null to clear the value. Times and repetition are checked by the service on the combined
    state (stored row + changes): turning a repetition off (`recurrence: none`) while the event has a
    `repeat_until` is a 422, unless the same body sends `repeat_until: null`.
    """

    model_config = _INPUT_CONFIG

    title: EventTitle = None
    description: EventDescription | None = None
    location: Location | None = None
    starts_on: StartsOn = None
    start_time: IsoTime | None = Field(default=None, description=START_TIME_DESCRIPTION)
    end_time: IsoTime | None = Field(default=None, description=END_TIME_DESCRIPTION)
    recurrence: Recurrence = Field(default=None, description=RECURRENCE_DESCRIPTION)
    repeat_until: IsoDate | None = Field(default=None, description=REPEAT_UNTIL_DESCRIPTION)


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None
    location: str | None
    starts_on: datetime.date
    start_time: datetime.time | None
    end_time: datetime.time | None
    recurrence: EventRecurrence
    repeat_until: datetime.date | None
    created_at: datetime.datetime
    updated_at: datetime.datetime


class OccurrenceView(Protocol):
    """An occurrence as the service hands it over: the day plus the ORM event."""

    date: datetime.date
    event: Any


class EventOccurrenceRead(BaseModel):
    """One day on which an event happens. A recurring event shows up once per day in the range."""

    date: datetime.date = Field(description="Dia desta ocorrência.")
    event: EventRead

    @classmethod
    def of(cls, occurrence: OccurrenceView) -> Self:
        return cls(date=occurrence.date, event=EventRead.model_validate(occurrence.event))


class DateRangeQuery(BaseModel):
    """`from` and `to` of a calendar listing: both required and inclusive, at most a year apart."""

    date_from: IsoDate = Field(alias="from", description="Primeiro dia (inclusive), AAAA-MM-DD.")
    date_to: IsoDate = Field(
        alias="to", description=f"Último dia (inclusive); no máximo {RANGE_MAX_DAYS} dias no total."
    )

    @model_validator(mode="after")
    def _check_range(self) -> Self:
        problem = range_problem(self.date_from, self.date_to)
        if problem:
            raise ValueError(problem)
        return self


class EventQuery(DateRangeQuery):
    """Query string of `GET /api/events`."""

    q: SearchText | None = Field(
        default=None, description="Busca no título, na descrição e no local, sem diferenciar maiúsculas."
    )
