import uuid
from datetime import date, datetime
from typing import Annotated, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from app.models.task import TaskPriority, TaskSort, TaskStatus
from app.schemas.common import DbText, IsoDate, NotNull, PageQuery

TITLE_MAX_LENGTH = 200  # tasks.title is VARCHAR(200)
DESCRIPTION_MAX_LENGTH = 5000
SEARCH_MAX_LENGTH = 200


def _normalize_title(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Informe o título.")
    if len(value) > TITLE_MAX_LENGTH:
        raise ValueError(f"O título deve ter no máximo {TITLE_MAX_LENGTH} caracteres.")
    return value


def _normalize_description(value: str) -> str | None:
    value = value.strip()
    if len(value) > DESCRIPTION_MAX_LENGTH:
        raise ValueError(f"A descrição deve ter no máximo {DESCRIPTION_MAX_LENGTH} caracteres.")
    return value or None


def _normalize_search(value: str) -> str | None:
    value = value.strip()
    if len(value) > SEARCH_MAX_LENGTH:
        raise ValueError(f"A busca deve ter no máximo {SEARCH_MAX_LENGTH} caracteres.")
    return value or None


TaskTitle = Annotated[DbText, AfterValidator(_normalize_title), NotNull]
# Blank (after strip) becomes None.
TaskDescription = Annotated[DbText, AfterValidator(_normalize_description)]
SearchText = Annotated[DbText, AfterValidator(_normalize_search)]
Status = Annotated[TaskStatus, NotNull]
Priority = Annotated[TaskPriority, NotNull]

# Unknown fields are rejected (422), not ignored: `completed_at`, `id` or `user_id` in the body are
# a client bug, and a silent drop would hide it. Enums are stored as their plain string values.
_INPUT_CONFIG = ConfigDict(extra="forbid", use_enum_values=True)


class TaskCreate(BaseModel):
    model_config = _INPUT_CONFIG

    title: TaskTitle
    description: TaskDescription | None = None
    status: Status = TaskStatus.TODO
    priority: Priority = TaskPriority.MEDIUM
    due_date: IsoDate | None = None


class TaskUpdate(BaseModel):
    """Partial update: only the fields present in the body change (see `model_fields_set`).

    `title`, `status` and `priority` may be omitted but not sent as null (NotNull, 422).
    `description` and `due_date` accept null to clear the value.
    """

    model_config = _INPUT_CONFIG

    title: TaskTitle = None
    description: TaskDescription | None = None
    status: Status = None
    priority: Priority = None
    due_date: IsoDate | None = None


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    due_date: date | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TaskQuery(PageQuery):
    """Query string of `GET /api/tasks`. Every filter is optional and they combine with AND."""

    model_config = ConfigDict(use_enum_values=True)

    status: list[TaskStatus] = Field(default=[], description="Um ou mais status (repita o parâmetro).")
    priority: list[TaskPriority] = Field(default=[], description="Uma ou mais prioridades.")
    due_from: IsoDate | None = Field(default=None, description="Prazo a partir desta data (inclusiva).")
    due_to: IsoDate | None = Field(default=None, description="Prazo até esta data (inclusiva).")
    overdue: bool = Field(
        default=False,
        description=(
            "true: só tarefas atrasadas (prazo antes de hoje, no fuso do servidor, e status diferente "
            "de done). false: sem filtro de atraso (não é o inverso de true)."
        ),
    )
    q: SearchText | None = Field(
        default=None, description="Busca no título e na descrição, sem diferenciar maiúsculas."
    )
    sort: TaskSort = Field(
        default=TaskSort.CREATED_AT_DESC,
        description="Ordenação; prefixo '-' para decrescente. Tarefas sem prazo ficam sempre por último.",
    )

    @model_validator(mode="after")
    def _check_due_range(self) -> Self:
        if self.due_from is not None and self.due_to is not None and self.due_from > self.due_to:
            raise ValueError("A data inicial (due_from) não pode ser posterior à data final (due_to).")
        return self
