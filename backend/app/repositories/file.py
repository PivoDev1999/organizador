import uuid
from collections.abc import Collection

from sqlalchemy import delete as delete_stmt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import File
from app.repositories.errors import flush


def get_for_user(
    db: Session, user_id: uuid.UUID, file_id: uuid.UUID, *, for_update: bool = False
) -> File | None:
    """The file row if it belongs to the user. `for_update=True` locks it (see `task.get_for_user`)."""
    stmt = select(File).where(File.id == file_id, File.user_id == user_id)
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return db.scalar(stmt)


def list_for_entity(db: Session, user_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID) -> list[File]:
    """The user's attachments of one record, newest first (`id` makes the order total)."""
    stmt = (
        select(File)
        .where(File.user_id == user_id, File.entity_type == entity_type, File.entity_id == entity_id)
        .order_by(File.created_at.desc(), File.id.asc())
    )
    return list(db.scalars(stmt).all())


def add(db: Session, file: File) -> File:
    """Insert and flush. The caller rolls back after an error."""
    db.add(file)
    flush(db)
    return file


def delete(db: Session, file: File) -> None:
    db.delete(file)
    flush(db)


def delete_for_entities(
    db: Session, user_id: uuid.UUID, entity_type: str, entity_ids: Collection[uuid.UUID]
) -> list[str]:
    """Delete the user's attachments of these records; returns the object keys to remove afterwards."""
    if not entity_ids:
        return []
    stmt = (
        delete_stmt(File)
        .where(
            File.user_id == user_id,
            File.entity_type == entity_type,
            File.entity_id.in_(list(entity_ids)),
        )
        .returning(File.object_key)
    )
    return list(db.scalars(stmt).all())


def ids_by_object_key(db: Session, bucket: str) -> dict[str, uuid.UUID]:
    """object_key -> file id of every row in the bucket (for the orphan cleanup)."""
    rows = db.execute(select(File.object_key, File.id).where(File.bucket == bucket)).all()
    return {key: file_id for key, file_id in rows}
