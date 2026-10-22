import logging

from fastapi import FastAPI

from app.api.errors import register_exception_handlers
from app.api.routers import auth, health, pantry, routines, shopping, tasks
from app.core.config import Settings, get_settings
from app.core.security import DEFAULT_BCRYPT_ROUNDS, dummy_password_hash

logger = logging.getLogger(__name__)

WEAK_BCRYPT_ROUNDS = 10


def prepare_password_hashing(settings: Settings) -> None:
    if settings.bcrypt_rounds < WEAK_BCRYPT_ROUNDS:
        logger.warning(
            "BCRYPT_ROUNDS=%d is too weak for production; use %d or more (default %d).",
            settings.bcrypt_rounds,
            WEAK_BCRYPT_ROUNDS,
            DEFAULT_BCRYPT_ROUNDS,
        )
    # Compute the login dummy hash now, so the first unknown e-mail is not slower (timing leak).
    dummy_password_hash(settings.bcrypt_rounds)


settings = get_settings()
prepare_password_hashing(settings)

app = FastAPI(title=settings.app_name, docs_url="/api/docs", openapi_url="/api/openapi.json")
register_exception_handlers(app)

app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
app.include_router(routines.router, prefix="/api")
app.include_router(pantry.router, prefix="/api")
app.include_router(shopping.router, prefix="/api")
