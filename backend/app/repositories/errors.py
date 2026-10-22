from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

UNIQUE_VIOLATION = "23505"


class DuplicateError(Exception):
    """A unique constraint or unique index was violated. `constraint` is its name."""

    def __init__(self, constraint: str | None) -> None:
        self.constraint = constraint
        super().__init__(f"duplicate value violates {constraint}")


def constraint_name(exc: IntegrityError) -> str | None:
    """Name of the violated constraint/index reported by Postgres (None for e.g. NOT NULL)."""
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None)


def is_unique_violation(exc: IntegrityError) -> bool:
    return getattr(exc.orig, "sqlstate", None) == UNIQUE_VIOLATION


def flush(db: Session) -> None:
    """Flush so constraint violations surface in the repository and not at commit time.

    Raises DuplicateError for unique violations; other integrity errors propagate unchanged.
    The caller owns the transaction and must roll back after an error.
    """
    try:
        db.flush()
    except IntegrityError as exc:
        if is_unique_violation(exc):
            raise DuplicateError(constraint_name(exc)) from exc
        raise
