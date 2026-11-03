from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, SettingsDep
from app.core.database import DbSession
from app.schemas.calendar import CalendarItemRead, calendar_item
from app.schemas.event import DateRangeQuery
from app.services import calendar as calendar_service

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("")
def get_calendar(
    query: Annotated[DateRangeQuery, Query()], db: DbSession, settings: SettingsDep, current_user: CurrentUser
) -> list[CalendarItemRead]:
    """Tudo o que cai entre `from` e `to` (inclusive, até 366 dias), só leitura. Só entram itens com data
    dentro de `[from, to]`: tarefas, contas e lembretes atrasados (de antes de `from`) ficam de fora; os
    atrasados aparecem no Painel (`GET /api/dashboard`).

    - `event`: ocorrências da agenda;
    - `task`: tarefas não concluídas com prazo no intervalo;
    - `bill`: despesas não pagas com vencimento no intervalo;
    - `pet`: lembretes dos pets (só o evento mais recente de cada série), pela próxima data.

    Ordem: data, itens sem horário primeiro, depois horário; empates na ordem event, task, bill, pet.
    Tudo é lido num mesmo instante (uma transação só de leitura, REPEATABLE READ).
    """
    entries = calendar_service.get_calendar(db, settings, current_user.id, query.date_from, query.date_to)
    return [calendar_item(entry) for entry in entries]
