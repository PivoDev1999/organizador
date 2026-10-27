from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, SettingsDep
from app.core.database import DbSession
from app.schemas.dashboard import DashboardQuery, DashboardRead
from app.services import dashboard as dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
def get_dashboard(
    query: Annotated[DashboardQuery, Query()], db: DbSession, settings: SettingsDep, current_user: CurrentUser
) -> DashboardRead:
    """Resumo do dia: tarefas, rotinas, despensa, mercado, pets e finanças, com as mesmas regras dos
    endpoints de cada módulo.

    As listas trazem até `limit` itens e o `total` completo (as rotinas de hoje vêm todas). Todos os
    números são lidos num mesmo instante (uma transação só de leitura, REPEATABLE READ).
    """
    dashboard = dashboard_service.get_dashboard(db, settings, current_user.id, query.within, query.limit)
    return DashboardRead.of(dashboard)
