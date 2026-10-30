"""Database probe of GET /api/status."""

from sqlalchemy import text
from sqlalchemy.orm import Session

# Upper bound of each probe query: a database that is up but stuck answers "unavailable" quickly.
STATEMENT_TIMEOUT_MS = 2000


def database_revision(db: Session) -> str | None:
    """Round trip to the database that also reads the Alembic revision applied to it (None if the table
    is empty). Raises SQLAlchemyError when the database cannot answer within the timeout."""
    db.execute(text(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}"))
    return db.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar_one_or_none()
