from fastapi import APIRouter, Response, status

from app.core.database import DbSession
from app.schemas.health import HealthResponse
from app.services.health import check_database

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(response: Response, db: DbSession) -> HealthResponse:
    if check_database(db):
        return HealthResponse(status="ok", database="ok")
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(status="degraded", database="unavailable")
