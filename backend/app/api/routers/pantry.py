import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, SettingsDep, StorageDep
from app.core.database import DbSession
from app.schemas.common import Page
from app.schemas.pantry import (
    PantryAlertsQuery,
    PantryAlertsRead,
    PantryItemCreate,
    PantryItemRead,
    PantryItemUpdate,
    PantryQuery,
    StockChange,
)
from app.services import pantry as pantry_service

router = APIRouter(prefix="/pantry", tags=["pantry"])


@router.get("")
def list_items(
    query: Annotated[PantryQuery, Query()], db: DbSession, settings: SettingsDep, current_user: CurrentUser
) -> Page[PantryItemRead]:
    views, total = pantry_service.list_items(db, settings, current_user.id, query)
    return Page[PantryItemRead].of([PantryItemRead.of(view) for view in views], total, query)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_item(
    data: PantryItemCreate, db: DbSession, settings: SettingsDep, current_user: CurrentUser
) -> PantryItemRead:
    return PantryItemRead.of(pantry_service.create_item(db, settings, current_user.id, data))


# Fixed paths are declared before "/{item_id}" so they are never parsed as an item id.
@router.get("/alerts")
def get_alerts(
    query: Annotated[PantryAlertsQuery, Query()],
    db: DbSession,
    settings: SettingsDep,
    current_user: CurrentUser,
) -> PantryAlertsRead:
    """Estoque baixo, vencidos e que vencem de hoje até hoje + `expiring_within` dias."""
    alerts = pantry_service.get_alerts(db, settings, current_user.id, query.expiring_within)
    return PantryAlertsRead(
        low_stock=[PantryItemRead.of(view) for view in alerts.low_stock],
        expired=[PantryItemRead.of(view) for view in alerts.expired],
        expiring_soon=[PantryItemRead.of(view) for view in alerts.expiring_soon],
    )


@router.get("/categories")
def list_categories(db: DbSession, current_user: CurrentUser) -> list[str]:
    """Categorias já usadas pelo usuário, em ordem alfabética."""
    return pantry_service.list_categories(db, current_user.id)


@router.get("/locations")
def list_locations(db: DbSession, current_user: CurrentUser) -> list[str]:
    """Locais já usados pelo usuário, em ordem alfabética."""
    return pantry_service.list_locations(db, current_user.id)


@router.get("/{item_id}")
def get_item(
    item_id: uuid.UUID, db: DbSession, settings: SettingsDep, current_user: CurrentUser
) -> PantryItemRead:
    return PantryItemRead.of(pantry_service.get_item_view(db, settings, current_user.id, item_id))


@router.patch("/{item_id}")
def update_item(
    item_id: uuid.UUID,
    data: PantryItemUpdate,
    db: DbSession,
    settings: SettingsDep,
    current_user: CurrentUser,
) -> PantryItemRead:
    return PantryItemRead.of(pantry_service.update_item(db, settings, current_user.id, item_id, data))


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: uuid.UUID, db: DbSession, storage: StorageDep, current_user: CurrentUser) -> None:
    pantry_service.delete_item(db, storage, current_user.id, item_id)


@router.post("/{item_id}/consume")
def consume(
    item_id: uuid.UUID, data: StockChange, db: DbSession, settings: SettingsDep, current_user: CurrentUser
) -> PantryItemRead:
    """Dá baixa de `amount`. Mais do que o estoque: 409 "Quantidade insuficiente."."""
    return PantryItemRead.of(pantry_service.consume(db, settings, current_user.id, item_id, data))


@router.post("/{item_id}/restock")
def restock(
    item_id: uuid.UUID, data: StockChange, db: DbSession, settings: SettingsDep, current_user: CurrentUser
) -> PantryItemRead:
    """Repõe `amount` no estoque."""
    return PantryItemRead.of(pantry_service.restock(db, settings, current_user.id, item_id, data))
