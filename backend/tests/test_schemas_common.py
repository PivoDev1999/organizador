import json
from datetime import UTC, date, datetime, time
from decimal import Decimal
from types import SimpleNamespace
from typing import Annotated

import pytest
from pydantic import BaseModel, ValidationError

from app.core.text import normalize_email, parse_email
from app.schemas.common import (
    MONEY_MAX,
    PAGE_DEFAULT_LIMIT,
    PAGE_MAX_LIMIT,
    PAGE_MAX_OFFSET,
    QUANTITY_MAX,
    DbText,
    Email,
    IsoDate,
    IsoTime,
    Money,
    NotNull,
    Page,
    PageQuery,
    Quantity,
    Utf8Str,
)


class Model(BaseModel):
    text: DbText = ""
    raw: Utf8Str = ""
    email: Email = "a@b.co"


@pytest.mark.parametrize("value", ["\x00", "a\x00b", "fim\x00"])
def test_db_text_rejects_nul_character(value):
    with pytest.raises(ValidationError, match="caractere nulo"):
        Model(text=value)


@pytest.mark.parametrize("field", ["text", "raw", "email"])
@pytest.mark.parametrize("value", ["\ud800", "a\udfffb", "R\ud800@example.test"])
def test_lone_surrogates_are_rejected(field, value):
    with pytest.raises(ValidationError, match="caracteres inválidos"):
        Model(**{field: value})


@pytest.mark.parametrize("value", ["", "texto comum", "acentuação e emoji \U0001f600", "\\x00 literal"])
def test_db_text_accepts_regular_text(value):
    assert Model(text=value).text == value


def test_utf8_str_accepts_nul():
    assert Model(raw="a\x00b").raw == "a\x00b"


def test_email_type_normalizes_and_validates():
    assert Model(email="  Ana@Example.TEST ").email == "ana@example.test"
    with pytest.raises(ValidationError, match="E-mail inválido."):
        Model(email="ana@example")


def test_normalize_email_only_trims_and_lowercases():
    assert normalize_email("  Ana@Example.TEST\n") == "ana@example.test"


@pytest.mark.parametrize("value", ["ana\x00@example.test", "ana@example", "a" * 243 + "@example.test"])
def test_parse_email_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        parse_email(value)


# --- NotNull, IsoDate, PageQuery and Page ------------------------------------------------------


class Partial(BaseModel):
    name: Annotated[str, NotNull] = None


def test_not_null_allows_omitting_the_field():
    partial = Partial()

    assert partial.name is None
    assert partial.model_fields_set == set()


def test_not_null_rejects_explicit_null():
    with pytest.raises(ValidationError, match="Este campo não pode ser nulo."):
        Partial(name=None)


def test_not_null_keeps_regular_values():
    assert Partial(name="Ana").name == "Ana"


class Dated(BaseModel):
    day: IsoDate | None = None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-05-10", date(2026, 5, 10)),
        ("2028-02-29", date(2028, 2, 29)),
        (date(2026, 1, 2), date(2026, 1, 2)),
    ],
    ids=["iso", "leap-day", "date-object"],
)
def test_iso_date_accepts_yyyy_mm_dd_and_date_objects(value, expected):
    assert Dated(day=value).day == expected


@pytest.mark.parametrize(
    "value",
    [
        "2026-05-10T00:00:00",
        "2026-05-10T00:00:00Z",
        "2026-05-10T00:00:00-03:00",
        "1778371200",
        1778371200,
        0,
        "20260510",
        "2026-5-10",
        "2026-02-30",
        "２０２６-０５-１０",
        " 2026-05-10",
        "2026-05-10\n",
        True,
        datetime(2026, 5, 10, tzinfo=UTC),
        b"2026-05-10",
    ],
    ids=[
        "datetime",
        "datetime-utc",
        "datetime-offset",
        "timestamp-string",
        "timestamp",
        "zero",
        "basic-format",
        "no-padding",
        "feb-30",
        "fullwidth-digits",
        "leading-space",
        "trailing-newline",
        "bool",
        "datetime-object",
        "bytes",
    ],
)
def test_iso_date_rejects_everything_else_without_echo(value):
    with pytest.raises(ValidationError) as exc_info:
        Dated(day=value)

    error = exc_info.value.errors()[0]
    assert str(error["ctx"]["error"]) == "Informe uma data válida no formato AAAA-MM-DD."


def test_iso_date_keeps_date_format_in_json_schema():
    schema = Dated.model_json_schema()["properties"]["day"]

    assert {"type": "string", "format": "date"} in schema["anyOf"]


def test_page_query_defaults_and_limits():
    assert (PageQuery().limit, PageQuery().offset) == (PAGE_DEFAULT_LIMIT, 0)
    for bad in ({"limit": 0}, {"limit": PAGE_MAX_LIMIT + 1}, {"offset": -1}, {"offset": PAGE_MAX_OFFSET + 1}):
        with pytest.raises(ValidationError):
            PageQuery(**bad)


class Row(BaseModel):
    model_config = {"from_attributes": True}

    name: str


def test_page_of_reads_items_from_attributes():
    items = [SimpleNamespace(name="a"), SimpleNamespace(name="b")]

    page = Page[Row].of(items, 7, PageQuery(limit=2, offset=4))

    assert page.model_dump() == {"items": [{"name": "a"}, {"name": "b"}], "total": 7, "limit": 2, "offset": 4}


# --- IsoTime -----------------------------------------------------------------------------------


class _TimeModel(BaseModel):
    at: IsoTime | None = None


@pytest.mark.parametrize(
    ("value", "expected"),
    [("07:30", time(7, 30)), ("23:59:59", time(23, 59, 59)), (time(6, 0), time(6, 0))],
)
def test_iso_time_accepts_hh_mm_and_hh_mm_ss(value, expected):
    assert _TimeModel(at=value).at == expected


@pytest.mark.parametrize(
    "value",
    [
        "7:30",
        "07:30Z",
        "07:30-03:00",
        "07:30:00.5",
        "24:00",
        "2026-10-21T07:30:00",
        3600,
        "3600",
        datetime(2026, 10, 21, 7, 30),
        time(7, 30, tzinfo=UTC),
    ],
)
def test_iso_time_rejects_other_formats(value):
    with pytest.raises(ValidationError) as exc_info:
        _TimeModel(at=value)
    assert exc_info.value.errors()[0]["msg"].endswith(
        "Informe um horário válido no formato HH:MM ou HH:MM:SS."
    )


# --- Quantity and Money (exact decimals) -------------------------------------------------------


class Amounts(BaseModel):
    quantity: Quantity | None = None
    money: Money | None = None


@pytest.mark.parametrize(
    ("field", "value", "json_value"),
    [
        ("quantity", "1.5", "1.500"),
        ("quantity", 1.5, "1.500"),
        ("quantity", 2, "2.000"),
        ("quantity", "0.1", "0.100"),
        ("quantity", "1.5000", "1.500"),
        ("quantity", "-0", "0.000"),
        ("quantity", str(QUANTITY_MAX), "9999999.999"),
        ("quantity", Decimal("0.250"), "0.250"),
        ("money", "10.5", "10.50"),
        ("money", 12, "12.00"),
        ("money", str(MONEY_MAX), "9999999999.99"),
    ],
)
def test_decimal_types_accept_strings_and_numbers_and_serialize_as_fixed_strings(field, value, json_value):
    model = Amounts(**{field: value})

    assert isinstance(getattr(model, field), Decimal)  # Python keeps exact Decimals
    assert json.loads(model.model_dump_json())[field] == json_value


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("quantity", "1.0001", "Use no máximo 3 casas decimais."),
        ("money", "1.001", "Use no máximo 2 casas decimais."),
        ("quantity", "10000000", "O valor deve ser no máximo 9999999.999."),
        ("money", 10**10, "O valor deve ser no máximo 9999999999.99."),
        *[("money", value, 'Envie valores em dinheiro como texto (ex.: "12.90").') for value in [0.1, 12.0]],
        ("quantity", "9" * 41, "Informe um número válido (ex.: 1.5)."),
        *[
            ("quantity", value, "Informe um número válido (ex.: 1.5).")
            for value in [
                "NaN",
                "Infinity",
                "1e3",
                "1E-2",
                "+1",
                ".5",
                "1.",
                " 1",
                "1,5",
                "",
                True,
                float("nan"),
                [1],
            ]
        ],
    ],
)
def test_decimal_types_reject_invalid_values(field, value, message):
    with pytest.raises(ValidationError) as exc_info:
        Amounts(**{field: value})

    assert [error["ctx"]["error"].args[0] for error in exc_info.value.errors()] == [message]


def test_money_input_schema_lists_integer_instead_of_number():
    money = Amounts.model_json_schema(mode="validation")["properties"]["money"]["anyOf"][0]

    assert [option.get("type") for option in money["anyOf"]] == ["string", "integer"]


def test_decimal_types_document_string_with_decimal_format():
    validation = Amounts.model_json_schema(mode="validation")["properties"]["quantity"]["anyOf"][0]
    serialization = Amounts.model_json_schema(mode="serialization")["properties"]["money"]["anyOf"][0]

    assert validation["anyOf"] == [
        {"type": "string", "format": "decimal", "pattern": r"^-?[0-9]+(\.[0-9]+)?$"},
        {"type": "number"},
    ]
    assert (serialization["type"], serialization["format"], serialization["examples"]) == (
        "string",
        "decimal",
        ["1.00"],
    )
