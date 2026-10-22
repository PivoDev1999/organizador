"""Fail early, with a clear message, when the PostgreSQL server lacks something the code relies on."""

from sqlalchemy import text

from app.repositories.search import TEXT_SORT_COLLATION


def test_text_sort_collation_is_available(db_session):
    found = db_session.scalar(
        text("SELECT count(*) FROM pg_collation WHERE collname = :name AND collprovider = 'i'"),
        {"name": TEXT_SORT_COLLATION},
    )
    assert found == 1, (
        f"PostgreSQL has no ICU collation {TEXT_SORT_COLLATION!r}: name sorting would fail with 500. "
        "Use the official postgres image from docker-compose.yml (built with ICU)."
    )
