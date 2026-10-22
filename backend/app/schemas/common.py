import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal
from typing import Annotated, Any, Self

from pydantic import AfterValidator, BaseModel, BeforeValidator, Field, PlainSerializer, WithJsonSchema

from app.core.text import check_db_text, check_utf8, parse_email

PAGE_DEFAULT_LIMIT = 20
PAGE_MAX_LIMIT = 100
# int4 max (2**31 - 1): far beyond any real list, and keeps OFFSET well inside Postgres' bigint.
PAGE_MAX_OFFSET = 2**31 - 1

ISO_DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
ISO_TIME_PATTERN = re.compile(r"[0-9]{2}:[0-9]{2}(:[0-9]{2})?")

# Valid UTF-8 (no lone surrogates). For text that never reaches the database, such as passwords.
Utf8Str = Annotated[str, AfterValidator(check_utf8)]
# Text safe to store in Postgres: valid UTF-8 and no NUL. Use it for every stored string field.
DbText = Annotated[str, AfterValidator(check_db_text)]
# Trimmed, lower-case and validated e-mail address.
Email = Annotated[str, AfterValidator(parse_email)]


def required_text(max_length: int, missing: str, too_long: str) -> Callable[[str], str]:
    """AfterValidator body: strip, then require 1..max_length characters."""

    def _normalize(value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError(missing)
        if len(value) > max_length:
            raise ValueError(too_long)
        return value

    return _normalize


def optional_text(max_length: int, too_long: str) -> Callable[[str], str | None]:
    """AfterValidator body: strip; blank becomes None; longer than max_length is an error."""

    def _normalize(value: str) -> str | None:
        value = value.strip()
        if len(value) > max_length:
            raise ValueError(too_long)
        return value or None

    return _normalize


def drop_blanks(values: list[str | None]) -> list[str]:
    """For repeated query params normalized by `optional_text`: blank ones mean "no filter"."""
    return [value for value in values if value]


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


def _parse_iso_time(value: Any) -> time:
    # Same strict spirit as IsoDate: only "HH:MM" or "HH:MM:SS" strings, a wall-clock time without
    # timezone or fraction. Lax mode would also take numbers (seconds since midnight), datetimes and
    # offsets such as "07:00Z". A naive `time` object is fine for Python callers.
    if type(value) is time and value.tzinfo is None:
        return value
    if isinstance(value, str) and ISO_TIME_PATTERN.fullmatch(value):
        try:
            return time.fromisoformat(value)
        except ValueError:
            pass
    raise ValueError("Informe um horário válido no formato HH:MM ou HH:MM:SS.")


# Time of day as "HH:MM" or "HH:MM:SS" (OpenAPI keeps `format: time`).
IsoTime = Annotated[time, BeforeValidator(_parse_iso_time)]


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


# --- Exact decimals (quantities, money) ----------------------------------------------------------
# JSON has no exact decimal type: a float would turn 0.1 + 0.2 into 0.30000000000000004. Decimals
# therefore travel as strings ("1.500"), and input also accepts JSON numbers for convenience. Values
# that do not fit the column (too many places, too large) are a 422, never rounded in silence.

# Plain decimal notation only: no exponent ("1e3"), no NaN/Infinity, no "+", no "1." or ".5".
DECIMAL_PATTERN = re.compile(r"-?[0-9]+(\.[0-9]+)?")
# Far beyond any NUMERIC(p, s) we use; caps the work of parsing absurd strings.
DECIMAL_MAX_STRING_LENGTH = 40
DECIMAL_MESSAGE = "Informe um número válido (ex.: 1.5)."
MONEY_FLOAT_MESSAGE = 'Envie valores em dinheiro como texto (ex.: "12.90").'


def _decimal_parser(places: int, max_digits: int, float_message: str | None = None):
    step = Decimal(1).scaleb(-places)  # 0.001 for 3 places
    largest = Decimal(10) ** (max_digits - places) - step  # 9999999.999 for NUMERIC(10, 3)
    largest_text = f"{largest:.{places}f}"

    def _parse(value: Any) -> Decimal:
        # bool is an int subclass: `true` would silently become 1.
        if isinstance(value, bool):
            raise ValueError(DECIMAL_MESSAGE)
        if isinstance(value, int):
            number = Decimal(value)
        elif isinstance(value, float):
            if float_message is not None:
                raise ValueError(float_message)
            # repr() is the shortest text that round-trips, so a JSON 0.1 becomes Decimal("0.1").
            number = Decimal(repr(value))
        elif isinstance(value, Decimal):
            number = value
        elif (
            isinstance(value, str)
            and len(value) <= DECIMAL_MAX_STRING_LENGTH
            and DECIMAL_PATTERN.fullmatch(value)
        ):
            number = Decimal(value)
        else:
            raise ValueError(DECIMAL_MESSAGE)
        if not number.is_finite():
            raise ValueError(DECIMAL_MESSAGE)
        if abs(number) > largest:
            raise ValueError(f"O valor deve ser no máximo {largest_text}.")
        # Safe now: at most `max_digits` integer digits, well inside the default 28-digit context.
        quantized = number.quantize(step)
        if quantized != number:
            raise ValueError(f"Use no máximo {places} casas decimais.")
        return quantized if quantized else abs(quantized)  # "-0" is just 0

    return _parse, largest


# Pydantic's own keywords for Decimal bounds -> standard JSON Schema keywords.
_BOUND_KEYWORDS = {"gt": "exclusiveMinimum", "ge": "minimum", "lt": "exclusiveMaximum", "le": "maximum"}


@dataclass(frozen=True)
class _DecimalJsonSchema:
    """OpenAPI for exact decimals: a decimal string (or number on input), keeping field bounds.

    Unlike WithJsonSchema, it starts from the schema Pydantic generated, so `Field(gt=0)` on the field
    still shows up (as `exclusiveMinimum`) and generated clients reject negative amounts too.
    """

    places: int
    largest: Decimal
    description: str
    # JSON type of the non-string input form: "number" (floats too) or "integer".
    number_type: str = "number"

    def __get_pydantic_json_schema__(self, core_schema: Any, handler: Any) -> dict[str, Any]:
        generated = handler(core_schema)
        bounds = {_BOUND_KEYWORDS[key]: float(generated[key]) for key in _BOUND_KEYWORDS if key in generated}
        bounds.setdefault("maximum", float(self.largest))
        string_schema = {"type": "string", "format": "decimal", "pattern": f"^{DECIMAL_PATTERN.pattern}$"}
        if handler.mode == "validation":
            schema = {"anyOf": [string_schema, {"type": self.number_type}]}
        else:
            schema = {**string_schema, "examples": [f"{Decimal(1):.{self.places}f}"]}
        # Numeric bounds apply to the number form; for the string form they document the allowed range.
        return {**schema, **bounds, "description": self.description}


def decimal_type(
    places: int,
    max_digits: int,
    description: str,
    *,
    allow_float: bool = True,
    float_message: str = DECIMAL_MESSAGE,
) -> Any:
    """Annotated `Decimal` for a `NUMERIC(max_digits, places)` column.

    Input: a decimal string ("1.5", "-2.25") or a JSON number; bool, NaN, Infinity, exponents and
    values that do not fit the column are rejected (422) instead of rounded. Output (JSON): a string
    with exactly `places` decimals ("1.500"). In Python (`model_dump()`), it stays a `Decimal`.
    Sign rules go on the field: `Annotated[Quantity, Field(ge=0)]` (they also appear in the OpenAPI).

    A JSON number is already a float when it arrives, so precision beyond ~15 significant digits (or a
    tiny value like 1e-400, which the JSON parser turns into 0) cannot be recovered. With
    `allow_float=False` only strings and integers are accepted: a float is a 422 with `float_message`
    and the OpenAPI input schema lists `integer` instead of `number`.
    """
    parse, largest = _decimal_parser(places, max_digits, None if allow_float else float_message)
    return Annotated[
        Decimal,
        BeforeValidator(parse),
        PlainSerializer(lambda value: f"{value:.{places}f}", return_type=str, when_used="json"),
        _DecimalJsonSchema(places, largest, description, "number" if allow_float else "integer"),
    ]


def decimal_output_type(places: int, description: str) -> Any:
    """Read-only `Decimal` without the column cap (computed totals): a fixed-places string in JSON."""
    return Annotated[
        Decimal,
        PlainSerializer(lambda value: f"{value:.{places}f}", return_type=str, when_used="json"),
        WithJsonSchema(
            {
                "type": "string",
                "format": "decimal",
                "pattern": f"^{DECIMAL_PATTERN.pattern}$",
                "examples": [f"{Decimal(1):.{places}f}"],
                "description": description,
            }
        ),
    ]


def decimal_max(places: int, max_digits: int) -> Decimal:
    """Largest value of a `NUMERIC(max_digits, places)` column, e.g. 9999999.999 for (10, 3)."""
    return _decimal_parser(places, max_digits)[1]


# NUMERIC(10, 3): pantry and shopping quantities (1.5 kg, 0.250 L).
QUANTITY_PLACES, QUANTITY_DIGITS = 3, 10
QUANTITY_MAX = decimal_max(QUANTITY_PLACES, QUANTITY_DIGITS)
Quantity = decimal_type(QUANTITY_PLACES, QUANTITY_DIGITS, "Número decimal com até 3 casas, como texto.")
# NUMERIC(12, 2): money (transactions, budgets, estimated prices). Same mechanism, 2 places.
MONEY_PLACES, MONEY_DIGITS = 2, 12
MONEY_MAX = decimal_max(MONEY_PLACES, MONEY_DIGITS)
# Signed by design: every money field must state its sign rule, e.g. Annotated[Money, Field(gt=0)].
# Floats are rejected: money must stay exact from the client on, so it travels as "12.90" (or 12).
Money = decimal_type(
    MONEY_PLACES,
    MONEY_DIGITS,
    "Valor em reais com até 2 casas, como texto.",
    allow_float=False,
    float_message=MONEY_FLOAT_MESSAGE,
)
# Sums of money (no column behind them, so no NUMERIC(12, 2) cap). Output only.
MoneyTotal = decimal_output_type(MONEY_PLACES, "Total em reais com 2 casas, como texto.")
