import pytest
from pydantic import BaseModel, ValidationError

from app.core.text import normalize_email, parse_email
from app.schemas.common import DbText, Email, Utf8Str


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
