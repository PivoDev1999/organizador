from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Annotated

import pytest
from pydantic import BaseModel, ValidationError

from app.core.text import normalize_email, parse_email
from app.schemas.common import (
    PAGE_DEFAULT_LIMIT,
    PAGE_MAX_LIMIT,
    PAGE_MAX_OFFSET,
    DbText,
    Email,
    IsoDate,
    NotNull,
    Page,
    PageQuery,
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
