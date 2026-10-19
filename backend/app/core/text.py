import re

EMAIL_MAX_LENGTH = 255
# Deliberately simple: one "@", no spaces, a dot in the domain. Deliverability is not checked.
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def check_utf8(value: str) -> str:
    """Reject strings that cannot be encoded as UTF-8 (lone surrogates such as "\\ud800" from JSON)."""
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("O texto contém caracteres inválidos.") from None
    return value


def check_db_text(value: str) -> str:
    """Text Postgres can store: valid UTF-8 and no NUL character."""
    check_utf8(value)
    if "\x00" in value:
        raise ValueError("O texto não pode conter o caractere nulo (\\x00).")
    return value


def normalize_email(value: str) -> str:
    return value.strip().lower()


def parse_email(value: str) -> str:
    """Normalize and validate an e-mail address; raise ValueError (in Portuguese) when invalid."""
    value = normalize_email(check_db_text(value))
    if len(value) > EMAIL_MAX_LENGTH or not EMAIL_PATTERN.fullmatch(value):
        raise ValueError("E-mail inválido.")
    return value
