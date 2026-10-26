import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentUser, SettingsDep
from app.core.database import DbSession
from app.schemas.finance import (
    BudgetCopyQuery,
    BudgetCopyRead,
    BudgetCreate,
    BudgetRead,
    BudgetUpdate,
    MonthQuery,
)
from app.services import budget as budget_service

router = APIRouter(prefix="/budgets", tags=["budgets"])


@router.get("")
def list_budgets(
    query: Annotated[MonthQuery, Query()], db: DbSession, settings: SettingsDep, current_user: CurrentUser
) -> list[BudgetRead]:
    """Orçamentos do mês (padrão: o atual), por categoria. `spent` soma as despesas do mês (pagas ou
    não) da categoria, sem diferenciar maiúsculas."""
    return [
        BudgetRead.of(view)
        for view in budget_service.list_budgets(db, settings, current_user.id, query.month)
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_budget(data: BudgetCreate, db: DbSession, current_user: CurrentUser) -> BudgetRead:
    """Já existe orçamento da categoria no mês (sem diferenciar maiúsculas): 409."""
    return BudgetRead.of(budget_service.create_budget(db, current_user.id, data))


# Fixed paths are declared before "/{budget_id}".
@router.post(
    "/copy",
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_200_OK: {"description": "Nenhum orçamento novo: `created` vazio."}},
)
def copy_budgets(
    query: Annotated[BudgetCopyQuery, Query()], response: Response, db: DbSession, current_user: CurrentUser
) -> BudgetCopyRead:
    """Copia os orçamentos de `from` para `to`, pulando as categorias que já existem no destino (sem
    diferenciar maiúsculas). 201 se criou algum, 200 se não criou nenhum."""
    result = budget_service.copy_budgets(db, current_user.id, query.source, query.target)
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return BudgetCopyRead.of(result)


@router.patch("/{budget_id}")
def update_budget(
    budget_id: uuid.UUID, data: BudgetUpdate, db: DbSession, current_user: CurrentUser
) -> BudgetRead:
    """Só o valor muda. Para trocar categoria ou mês, apague e crie outro."""
    return BudgetRead.of(budget_service.update_budget(db, current_user.id, budget_id, data))


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_budget(budget_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> None:
    budget_service.delete_budget(db, current_user.id, budget_id)
