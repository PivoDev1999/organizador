from fastapi import APIRouter

from app.api.deps import CurrentUser, SettingsDep, StorageDep
from app.core.database import DbSession
from app.schemas.status import SystemStatusRead
from app.services import status as status_service

router = APIRouter(tags=["health"])


@router.get("/status")
def get_status(
    db: DbSession, storage: StorageDep, settings: SettingsDep, current_user: CurrentUser
) -> SystemStatusRead:
    """Status do sistema: versão, horário e uptime da API, e a situação do banco, dos arquivos (Garage)
    e do último backup.

    Responde 200 mesmo com um serviço fora do ar: cada bloco traz o seu status, e `overall` resume:
    `down` sem banco, `degraded` com os arquivos indisponíveis ou o backup atrasado, ausente ou ilegível,
    `ok` no resto. Para o healthcheck do container e do proxy, use `GET /api/health` (público e leve).
    """
    return status_service.get_system_status(db, storage, settings)
