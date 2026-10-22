import uuid
from datetime import date, datetime, time
from typing import Annotated, Any, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictInt, model_validator

from app.core.schedule import schedule_problem
from app.models.routine import RoutineFrequency, RoutineSort
from app.schemas.common import DbText, IsoDate, IsoTime, NotNull, PageQuery

NAME_MAX_LENGTH = 200  # routines.name is VARCHAR(200)
DESCRIPTION_MAX_LENGTH = 5000
NOTE_MAX_LENGTH = 5000
SEARCH_MAX_LENGTH = 200


def _normalize_name(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Informe o nome.")
    if len(value) > NAME_MAX_LENGTH:
        raise ValueError(f"O nome deve ter no máximo {NAME_MAX_LENGTH} caracteres.")
    return value


def _optional_text(max_length: int, message: str):
    def _normalize(value: str) -> str | None:
        value = value.strip()
        if len(value) > max_length:
            raise ValueError(message)
        return value or None

    return _normalize


def _normalize_days(value: list[int]) -> list[int] | None:
    # Order and repetition carry no meaning: store each weekday once, sorted. [] means "no days".
    return sorted(set(value)) or None


RoutineName = Annotated[DbText, AfterValidator(_normalize_name), NotNull]
# Blank (after strip) becomes None.
RoutineDescription = Annotated[
    DbText,
    AfterValidator(
        _optional_text(
            DESCRIPTION_MAX_LENGTH, f"A descrição deve ter no máximo {DESCRIPTION_MAX_LENGTH} caracteres."
        )
    ),
]
LogNote = Annotated[
    DbText,
    AfterValidator(
        _optional_text(NOTE_MAX_LENGTH, f"A observação deve ter no máximo {NOTE_MAX_LENGTH} caracteres.")
    ),
]
SearchText = Annotated[
    DbText,
    AfterValidator(
        _optional_text(SEARCH_MAX_LENGTH, f"A busca deve ter no máximo {SEARCH_MAX_LENGTH} caracteres.")
    ),
]
# Strict ints: "3", 3.0 or true are a client bug, not a weekday.
Weekday = Annotated[StrictInt, Field(ge=0, le=6)]
DaysOfWeek = Annotated[
    list[Weekday],
    AfterValidator(_normalize_days),
    Field(description="Dias da semana: 0 = domingo ... 6 = sábado. Só para rotinas semanais."),
]
DayOfMonth = Annotated[
    StrictInt,
    Field(
        ge=1,
        le=31,
        description="Dia do mês (1-31). Só para mensais; em meses mais curtos, vale o último dia.",
    ),
]
Frequency = Annotated[RoutineFrequency, NotNull]
Active = Annotated[bool, NotNull]

# Unknown fields are rejected (422), not ignored. Enums are stored as their plain string values.
_INPUT_CONFIG = ConfigDict(extra="forbid", use_enum_values=True)


class RoutineCreate(BaseModel):
    model_config = _INPUT_CONFIG

    name: RoutineName
    description: RoutineDescription | None = None
    frequency: Frequency
    days_of_week: DaysOfWeek | None = None
    day_of_month: DayOfMonth | None = None
    time_of_day: IsoTime | None = None
    is_active: Active = True

    @model_validator(mode="after")
    def _check_schedule(self) -> Self:
        problem = schedule_problem(self.frequency, self.days_of_week, self.day_of_month)
        if problem:
            raise ValueError(problem)
        return self


class RoutineUpdate(BaseModel):
    """Partial update: only the fields present in the body change (see `model_fields_set`).

    `name`, `frequency` and `is_active` may be omitted but not sent as null (NotNull, 422). The others
    accept null to clear the value. The schedule is checked by the service on the combined state
    (stored row + changes), because it depends on fields the body may not carry.
    """

    model_config = _INPUT_CONFIG

    name: RoutineName = None
    description: RoutineDescription | None = None
    frequency: Frequency = None
    days_of_week: DaysOfWeek | None = None
    day_of_month: DayOfMonth | None = None
    time_of_day: IsoTime | None = None
    is_active: Active = None


class RoutineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    frequency: RoutineFrequency
    days_of_week: list[int] | None
    day_of_month: int | None
    time_of_day: time | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class RoutineTodayRead(RoutineRead):
    done_today: bool = Field(description="Já marcada como feita hoje (no fuso do servidor).")

    @classmethod
    def of(cls, routine: Any, done_today: bool) -> Self:
        """Build from an ORM routine (read via attributes) plus the flag computed by the service."""
        return cls(**RoutineRead.model_validate(routine).model_dump(), done_today=done_today)


class RoutineLogCreate(BaseModel):
    model_config = _INPUT_CONFIG

    done_on: IsoDate | None = Field(default=None, description="Dia em que foi feita; padrão: hoje.")
    note: LogNote | None = None


class RoutineLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    routine_id: uuid.UUID
    done_on: date
    note: str | None
    created_at: datetime


class RoutineQuery(PageQuery):
    """Query string of `GET /api/routines`. Every filter is optional and they combine with AND."""

    model_config = ConfigDict(use_enum_values=True)

    frequency: list[RoutineFrequency] = Field(
        default=[], description="Uma ou mais frequências (repita o parâmetro)."
    )
    is_active: bool | None = Field(default=None, description="true: só ativas; false: só inativas.")
    q: SearchText | None = Field(default=None, description="Busca no nome, sem diferenciar maiúsculas.")
    sort: RoutineSort = Field(
        default=RoutineSort.NAME, description="Ordenação; prefixo '-' para decrescente."
    )


class RoutineLogQuery(PageQuery):
    """Query string of `GET /api/routines/{id}/logs`. Newest first."""

    date_from: IsoDate | None = Field(
        default=None, alias="from", description="A partir desta data (inclusiva)."
    )
    date_to: IsoDate | None = Field(default=None, alias="to", description="Até esta data (inclusiva).")

    @model_validator(mode="after")
    def _check_range(self) -> Self:
        if self.date_from is not None and self.date_to is not None and self.date_from > self.date_to:
            raise ValueError("A data inicial (from) não pode ser posterior à data final (to).")
        return self
