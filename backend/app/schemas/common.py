import re
from collections.abc import Iterable
from datetime import date
from typing import Annotated, Any, Self

from pydantic import AfterValidator, BaseModel, BeforeValidator, Field

from app.core.text import check_db_text, check_utf8, parse_email

PAGE_DEFAULT_LIMIT = 20
PAGE_MAX_LIMIT = 100
# int4 max (2**31 - 1): far beyond any real list, and keeps OFFSET well inside Postgres' bigint.
PAGE_MAX_OFFSET = 2**31 - 1

ISO_DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")

# Valid UTF-8 (no lone surrogates). For text that never reaches the database, such as passwords.
Utf8Str = Annotated[str, AfterValidator(check_utf8)]
# Text safe to store in Postgres: valid UTF-8 and no NUL. Use it for every stored string field.
DbText = Annotated[str, AfterValidator(check_db_text)]
# Trimmed, lower-case and validated e-mail address.
Email = Annotated[str, AfterValidator(parse_email)]


def _reject_null(value: Any) -> Any:
    if value is None:
        raise ValueError("Este campo não pode ser nulo.")
    return value


# For optional-but-not-nullable fields of partial updates: `field: Annotated[X, NotNull] = None`.
# Defaults are not validated, so omitting the field is fine; an explicit null is a 422.
NotNull = BeforeValidator(_reject_null)


def _parse_iso_date(value: Any) -> date:
    # Strict contract: only "YYYY-MM-DD" strings. Pydantic's lax mode would also accept datetimes at
    # midnight and Unix timestamps (numbers or numeric strings). A real `date` object is fine (Python
    # callers; JSON and query strings never produce one), but not a `datetime`, its subclass.
    if type(value) is date:
        return value
    if isinstance(value, str) and ISO_DATE_PATTERN.fullmatch(value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise ValueError("Informe uma data válida no formato AAAA-MM-DD.")


# Calendar date as a "YYYY-MM-DD" string (OpenAPI keeps `format: date`).
IsoDate = Annotated[date, BeforeValidator(_parse_iso_date)]


class PageQuery(BaseModel):
    """Pagination query params. List queries inherit from it."""

    limit: int = Field(default=PAGE_DEFAULT_LIMIT, ge=1, le=PAGE_MAX_LIMIT)
    offset: int = Field(default=0, ge=0, le=PAGE_MAX_OFFSET)


class Page[T](BaseModel):
    """One page of a paginated list. `total` counts every match of the filters, ignoring limit/offset."""

    items: list[T]
    total: int
    limit: int
    offset: int

    @classmethod
    def of(cls, items: Iterable[Any], total: int, query: PageQuery) -> Self:
        """Build the page from ORM objects (read via attributes) and the query that produced them."""
        return cls.model_validate(
            {"items": list(items), "total": total, "limit": query.limit, "offset": query.offset},
            from_attributes=True,
        )
