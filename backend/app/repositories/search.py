"""Helpers for text search shared by the repositories."""

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
