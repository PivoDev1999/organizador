import uuid

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import User
from app.repositories.errors import flush


def get_by_id(db: Session, user_id: uuid.UUID) -> User | None:
    return db.get(User, user_id)


def get_by_email(db: Session, normalized_email: str) -> User | None:
    """Case-insensitive lookup.

    Contract: `normalized_email` must come from `core.text.parse_email` (trimmed, lower-case, valid
    UTF-8 without NUL). Raw user input can make Postgres fail (NUL) and is not normalized here.
    """
    return db.scalar(select(User).where(func.lower(User.email) == normalized_email))


def add(db: Session, user: User) -> User:
    """Insert and flush, so constraint violations surface here and not at commit time.

    Raises DuplicateError for unique violations; other integrity errors propagate unchanged.
    The caller owns the transaction and must roll back after an error.
    """
    db.add(user)
    flush(db)
    return user


def update_password_hash(db: Session, user_id: uuid.UUID, old_hash: str, new_hash: str) -> bool:
    """Compare-and-set: only replaces the hash if it is still `old_hash`. Returns whether a row changed."""
    result = db.execute(
        update(User)
        .where(User.id == user_id, User.password_hash == old_hash)
        .values(password_hash=new_hash)
        .execution_options(synchronize_session="fetch")
    )
    return result.rowcount == 1
