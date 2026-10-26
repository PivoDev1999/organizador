import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentUser, SettingsDep, StorageDep
from app.core.database import DbSession
from app.schemas.common import Page
from app.schemas.shopping import (
    ShoppingItemCreate,
    ShoppingItemRead,
    ShoppingItemUpdate,
    ShoppingPurchaseRead,
    ShoppingQuery,
    ShoppingSummaryRead,
)
from app.services import shopping as shopping_service

router = APIRouter(prefix="/shopping", tags=["shopping"])


@router.get("")
def list_items(
    query: Annotated[ShoppingQuery, Query()], db: DbSession, current_user: CurrentUser
) -> Page[ShoppingItemRead]:
    items, total = shopping_service.list_items(db, current_user.id, query)
    return Page[ShoppingItemRead].of(items, total, query)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_item(data: ShoppingItemCreate, db: DbSession, current_user: CurrentUser) -> ShoppingItemRead:
    """Item da despensa (`pantry_item_id`) inexistente ou de outro usuário: 422."""
    return ShoppingItemRead.model_validate(shopping_service.create_item(db, current_user.id, data))


# Fixed paths are declared before "/{item_id}" so they are never parsed as an item id.
@router.get("/summary")
def get_summary(db: DbSession, current_user: CurrentUser) -> ShoppingSummaryRead:
    """Contagem de pendentes e comprados e o total estimado dos pendentes."""
    return ShoppingSummaryRead.model_validate(shopping_service.get_summary(db, current_user.id))


@router.post(
    "/from-pantry",
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_200_OK: {"description": "Nenhum item novo: devolve `[]`."}},
)
def create_from_pantry(
    response: Response,
    db: DbSession,
    settings: SettingsDep,
    current_user: CurrentUser,
    include_expired: Annotated[
        bool, Query(description="Incluir também os itens vencidos (no fuso do servidor).")
    ] = False,
) -> list[ShoppingItemRead]:
    """Gera itens da lista a partir da despensa com estoque baixo.

    Pula os itens da despensa que já têm um item pendente ligado, então repetir a chamada não duplica
    nada. A quantidade sugerida é o que falta para o mínimo (vazia se nada falta). Devolve só os itens
    criados: 201 se criou algum, 200 com `[]` se não criou nenhum.
    """
    items = shopping_service.create_from_pantry(
        db, settings, current_user.id, include_expired=include_expired
    )
    if not items:
        response.status_code = status.HTTP_200_OK
    return [ShoppingItemRead.model_validate(item) for item in items]


@router.delete("/purchased", status_code=status.HTTP_204_NO_CONTENT)
def delete_purchased(db: DbSession, storage: StorageDep, current_user: CurrentUser) -> None:
    """Apaga todos os itens já comprados do usuário, com os anexos deles."""
    shopping_service.delete_purchased(db, storage, current_user.id)


@router.get("/{item_id}")
def get_item(item_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> ShoppingItemRead:
    return ShoppingItemRead.model_validate(shopping_service.get_item(db, current_user.id, item_id))


@router.patch("/{item_id}")
def update_item(
    item_id: uuid.UUID, data: ShoppingItemUpdate, db: DbSession, current_user: CurrentUser
) -> ShoppingItemRead:
    """Altera só os campos enviados. Para marcar como comprado, use `/purchase` e `/unpurchase`."""
    return ShoppingItemRead.model_validate(shopping_service.update_item(db, current_user.id, item_id, data))


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: uuid.UUID, db: DbSession, storage: StorageDep, current_user: CurrentUser) -> None:
    shopping_service.delete_item(db, storage, current_user.id, item_id)


@router.post("/{item_id}/purchase")
def purchase(item_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> ShoppingPurchaseRead:
    """Marca como comprado. Se o item estiver ligado à despensa, tiver quantidade e a mesma unidade
    (sem diferenciar maiúsculas e espaços), repõe o estoque na mesma operação (`pantry_restocked`).

    Já comprado: 409. Reposição acima do limite do estoque: 422 e nada é gravado.
    """
    return ShoppingPurchaseRead.of(shopping_service.purchase(db, current_user.id, item_id))


@router.post("/{item_id}/unpurchase")
def unpurchase(item_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> ShoppingItemRead:
    """Volta o item para pendente. Não mexe na despensa: uma reposição feita na compra continua
    lá (ajuste o estoque na despensa, se precisar). Item não comprado: 409. Já existe outro item
    pendente ligado ao mesmo item da despensa (ex.: criado pelo `from-pantry`): 409.
    """
    return ShoppingItemRead.model_validate(shopping_service.unpurchase(db, current_user.id, item_id))
