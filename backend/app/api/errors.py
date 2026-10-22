from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from app.core.errors import (
    ConcurrentChangeError,
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)

STATUS_BY_ERROR: dict[type[DomainError], int] = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    ForbiddenError: status.HTTP_403_FORBIDDEN,
    UnauthorizedError: status.HTTP_401_UNAUTHORIZED,
    ValidationError: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


def _status_for(exc: DomainError) -> int:
    for cls in type(exc).__mro__:
        if cls in STATUS_BY_ERROR:
            return STATUS_BY_ERROR[cls]
    return status.HTTP_400_BAD_REQUEST


async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    status_code = _status_for(exc)
    headers = {"WWW-Authenticate": "Bearer"} if status_code == status.HTTP_401_UNAUTHORIZED else None
    if isinstance(exc, ValidationError):
        # Same shape as Pydantic's 422, so clients handle every validation error the same way.
        body = [{"type": "value_error", "loc": ["body"], "msg": exc.detail}]
        return JSONResponse({"detail": body}, status_code=status_code)
    return JSONResponse({"detail": exc.detail}, status_code=status_code, headers=headers)


# deadlock_detected and serialization_failure: the database aborted this transaction to let a
# concurrent one finish. Nothing was saved and retrying usually works, so it is a 409, not a 500.
RETRYABLE_SQLSTATES = frozenset({"40P01", "40001"})


async def operational_error_handler(request: Request, exc: OperationalError) -> JSONResponse:
    """Safety net for lock conflicts the services did not prevent. Other OperationalErrors (database
    down, timeouts) are re-raised and stay 500."""
    if getattr(exc.orig, "sqlstate", None) not in RETRYABLE_SQLSTATES:
        raise exc
    return JSONResponse({"detail": ConcurrentChangeError.detail}, status_code=status.HTTP_409_CONFLICT)


def _safe_text(value: Any) -> Any:
    # Lone surrogates cannot be serialized to JSON; replace them instead of failing with 500.
    return value.encode("utf-8", "replace").decode() if isinstance(value, str) else value


DATE_MESSAGE = "Informe uma data válida no formato AAAA-MM-DD."
INTEGER_MESSAGE = "Informe um número inteiro."
OBJECT_MESSAGE = "Informe um objeto JSON."
FALLBACK_MESSAGE = "Valor inválido."

# Portuguese message per Pydantic error type. Placeholders come only from the error `ctx` keys
# gt, ge, le, min_length, max_length and expected, which describe the schema, never the received value.
MESSAGES_BY_TYPE: dict[str, str] = {
    "missing": "Campo obrigatório.",
    "string_type": "Informe um texto.",
    "extra_forbidden": "Campo não permitido.",
    "enum": "Valor inválido. Use um destes: {expected}.",
    "literal_error": "Valor inválido. Use um destes: {expected}.",
    "bool_parsing": "Informe true ou false.",
    "int_parsing": INTEGER_MESSAGE,
    "int_type": INTEGER_MESSAGE,
    "date_parsing": DATE_MESSAGE,
    "date_from_datetime_parsing": DATE_MESSAGE,
    "date_type": DATE_MESSAGE,
    "uuid_parsing": "Identificador inválido.",
    "greater_than": "O valor deve ser maior que {gt}.",
    "greater_than_equal": "O valor deve ser maior ou igual a {ge}.",
    "less_than_equal": "O valor deve ser menor ou igual a {le}.",
    "string_too_long": "O texto deve ter no máximo {max_length} caracteres.",
    "string_too_short": "O texto deve ter pelo menos {min_length} caracteres.",
    "json_invalid": "JSON inválido.",
    "model_attributes_type": OBJECT_MESSAGE,
    "dict_type": OBJECT_MESSAGE,
    "list_type": "Informe uma lista.",
}
SAFE_CTX_KEYS = ("gt", "ge", "le", "min_length", "max_length", "expected")


def _message(error: dict[str, Any]) -> str:
    ctx = error.get("ctx") or {}
    if error["type"] == "value_error" and "error" in ctx:
        # Our own validator message, without Pydantic's "Value error, " prefix. Validator messages go
        # straight to the client, so they must never include the received value.
        return str(ctx["error"])
    template = MESSAGES_BY_TYPE.get(error["type"], FALLBACK_MESSAGE)
    params = {key: str(ctx[key]).replace(" or ", " ou ") for key in SAFE_CTX_KEYS if key in ctx}
    try:
        return template.format_map(params)
    except KeyError:
        return FALLBACK_MESSAGE


def _public_error(error: dict[str, Any]) -> dict[str, Any]:
    """Validation error without `input`, `ctx` and `url`: never echo what the user typed (passwords).

    Pydantic's own English messages are replaced too: some of them quote the input (uuid_parsing).
    """
    return {
        "type": error["type"],
        "loc": [_safe_text(part) for part in error["loc"]],
        "msg": _safe_text(_message(error)),
    }


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        {"detail": [_public_error(error) for error in exc.errors()]},
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, domain_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(OperationalError, operational_error_handler)
