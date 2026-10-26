import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Query, status

from app.api.deps import CurrentUser, SettingsDep, StorageDep
from app.core.database import DbSession
from app.schemas.common import Page
from app.schemas.finance import (
    MonthQuery,
    SummaryRead,
    TransactionCreate,
    TransactionPay,
    TransactionQuery,
    TransactionRead,
    TransactionUpdate,
    UpcomingQuery,
)
from app.services import transaction as transaction_service

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("")
def list_transactions(
    query: Annotated[TransactionQuery, Query()],
    db: DbSession,
    settings: SettingsDep,
    current_user: CurrentUser,
) -> Page[TransactionRead]:
    views, total = transaction_service.list_transactions(db, settings, current_user.id, query)
    return Page[TransactionRead].of([TransactionRead.of(view) for view in views], total, query)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_transaction(
    data: TransactionCreate, db: DbSession, settings: SettingsDep, current_user: CurrentUser
) -> TransactionRead:
    """Com `paid_on`, a transação já nasce paga. Pet (`pet_id`) inexistente ou de outro usuário: 422."""
    return TransactionRead.of(transaction_service.create_transaction(db, settings, current_user.id, data))


# Fixed paths are declared before "/{transaction_id}" so they are never parsed as an id.
@router.get("/upcoming")
def list_upcoming(
    query: Annotated[UpcomingQuery, Query()], db: DbSession, settings: SettingsDep, current_user: CurrentUser
) -> list[TransactionRead]:
    """Contas a pagar: despesas pendentes com vencimento até hoje + `within` dias, incluindo as
    atrasadas (`overdue`), por vencimento e id."""
    views = transaction_service.list_upcoming(db, settings, current_user.id, query.within)
    return [TransactionRead.of(view) for view in views]


@router.get("/summary")
def get_summary(
    query: Annotated[MonthQuery, Query()], db: DbSession, settings: SettingsDep, current_user: CurrentUser
) -> SummaryRead:
    """Resumo do mês em regime de competência: entra tudo que vence no mês, pago ou não.

    `by_category` agrupa sem diferenciar maiúsculas e mostra a grafia da transação criada mais
    recentemente do grupo.
    """
    return SummaryRead.of(transaction_service.get_summary(db, settings, current_user.id, query.month))


@router.get("/categories")
def list_categories(db: DbSession, current_user: CurrentUser) -> list[str]:
    """Categorias já usadas, sem repetir variações de maiúsculas (vale a grafia mais recente), em
    ordem alfabética."""
    return transaction_service.list_categories(db, current_user.id)


@router.get("/{transaction_id}")
def get_transaction(
    transaction_id: uuid.UUID, db: DbSession, settings: SettingsDep, current_user: CurrentUser
) -> TransactionRead:
    return TransactionRead.of(transaction_service.get_view(db, settings, current_user.id, transaction_id))


@router.patch("/{transaction_id}")
def update_transaction(
    transaction_id: uuid.UUID,
    data: TransactionUpdate,
    db: DbSession,
    settings: SettingsDep,
    current_user: CurrentUser,
) -> TransactionRead:
    """Altera só os campos enviados. Para pagar ou desfazer o pagamento, use `/pay` e `/unpay`."""
    view = transaction_service.update_transaction(db, settings, current_user.id, transaction_id, data)
    return TransactionRead.of(view)


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(
    transaction_id: uuid.UUID, db: DbSession, storage: StorageDep, current_user: CurrentUser
) -> None:
    transaction_service.delete_transaction(db, storage, current_user.id, transaction_id)


@router.post("/{transaction_id}/pay")
def pay(
    transaction_id: uuid.UUID,
    db: DbSession,
    settings: SettingsDep,
    current_user: CurrentUser,
    data: Annotated[TransactionPay | None, Body()] = None,
) -> TransactionRead:
    """Marca como paga em `paid_on` (padrão: hoje, no fuso do servidor; futuro: 422). Já paga: 409."""
    paid_on = data.paid_on if data is not None else None
    return TransactionRead.of(transaction_service.pay(db, settings, current_user.id, transaction_id, paid_on))


@router.post("/{transaction_id}/unpay")
def unpay(
    transaction_id: uuid.UUID, db: DbSession, settings: SettingsDep, current_user: CurrentUser
) -> TransactionRead:
    """Volta a transação para pendente. Não paga: 409."""
    return TransactionRead.of(transaction_service.unpay(db, settings, current_user.id, transaction_id))
