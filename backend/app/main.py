import logging

from fastapi import FastAPI

from app.api.errors import register_exception_handlers
from app.api.middleware import FilesSecurityHeaders, UploadBodyLimit
from app.api.request_id import RequestIdMiddleware
from app.api.routers import (
    auth,
    budgets,
    dashboard,
    docs,
    files,
    health,
    pantry,
    pets,
    routines,
    shopping,
    status,
    tasks,
    transactions,
)
from app.core.config import Settings, get_settings
from app.core.logs import configure_logging
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


configure_logging()
settings = get_settings()
prepare_password_hashing(settings)

# The default /docs page loads Swagger UI from a CDN: the docs router serves it locally instead.
app = FastAPI(title=settings.app_name, docs_url=None, redoc_url=None, openapi_url=docs.OPENAPI_URL)
register_exception_handlers(app)
# The last one added runs first: the security headers also cover the early 413 of the body limit, and the
# request id (outermost) covers every response and logs one access line per request.
app.add_middleware(UploadBodyLimit)
app.add_middleware(FilesSecurityHeaders)
app.add_middleware(RequestIdMiddleware)

app.include_router(health.router, prefix="/api")
app.include_router(status.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
app.include_router(routines.router, prefix="/api")
app.include_router(pantry.router, prefix="/api")
app.include_router(shopping.router, prefix="/api")
app.include_router(pets.router, prefix="/api")
app.include_router(transactions.router, prefix="/api")
app.include_router(budgets.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(docs.router)
