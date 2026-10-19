from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.errors import ConflictError, DomainError, ForbiddenError, NotFoundError, UnauthorizedError

STATUS_BY_ERROR: dict[type[DomainError], int] = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    ForbiddenError: status.HTTP_403_FORBIDDEN,
    UnauthorizedError: status.HTTP_401_UNAUTHORIZED,
}


def _status_for(exc: DomainError) -> int:
    for cls in type(exc).__mro__:
        if cls in STATUS_BY_ERROR:
            return STATUS_BY_ERROR[cls]
    return status.HTTP_400_BAD_REQUEST


async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    status_code = _status_for(exc)
    headers = {"WWW-Authenticate": "Bearer"} if status_code == status.HTTP_401_UNAUTHORIZED else None
    return JSONResponse({"detail": exc.detail}, status_code=status_code, headers=headers)


def _safe_text(value: Any) -> Any:
    # Lone surrogates cannot be serialized to JSON; replace them instead of failing with 500.
    return value.encode("utf-8", "replace").decode() if isinstance(value, str) else value


def _public_error(error: dict[str, Any]) -> dict[str, Any]:
    """Validation error without `input`, `ctx` and `url`: never echo what the user typed (passwords)."""
    message = error["msg"]
    if error["type"] == "value_error" and "error" in error.get("ctx", {}):
        # Our own validator message, without Pydantic's "Value error, " prefix. Validator messages go
        # straight to the client, so they must never include the received value.
        message = str(error["ctx"]["error"])
    return {
        "type": error["type"],
        "loc": [_safe_text(part) for part in error["loc"]],
        "msg": _safe_text(message),
    }


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        {"detail": [_public_error(error) for error in exc.errors()]},
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, domain_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
