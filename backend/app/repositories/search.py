"""Helpers for text search shared by the repositories."""

from typing import Any

from sqlalchemy import ColumnElement, String, cast, func

LIKE_ESCAPE = "\\"


def escape_like(term: str) -> str:
    """Escape LIKE wildcards so `%`, `_` and the escape character itself match literally."""
    return (
        term.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", LIKE_ESCAPE + "%")
        .replace("_", LIKE_ESCAPE + "_")
    )


# Collation for sorting human text. The Alpine Postgres image uses musl, whose "en_US.utf8" sorts
# byte-wise like "C" (uppercase before lowercase, accented letters last). ICU's Brazilian Portuguese
# collation, shipped with the official image, gives "agua, Água, banho, Faxina". Applied per query
# (ORDER BY ... COLLATE), so it needs no schema change.
TEXT_SORT_COLLATION = "pt-BR-x-icu"


def case_insensitive_key(expression: Any) -> ColumnElement[str]:
    """SQL twin of `str.lower()` for case-insensitive equality and grouping (see app.core.finance).

    The ICU collation makes lower() follow the full Unicode mapping, like Python; the default musl
    collation does not ("İ", final sigma). Accents and whitespace still count.
    """
    if isinstance(expression, str):
        # Typed parameter: COLLATE is not allowed on a parameter of unknown type.
        expression = cast(expression, String)
    return func.lower(expression.collate(TEXT_SORT_COLLATION))
