"""Attachments (Arquivos): upload, download, listing and deletion of files linked to any record.

Storage and database are not one transaction, so the order of the steps decides what a failure leaves:

- Upload: object first, then the row. If the row cannot be saved, the object is deleted; if that delete
  fails too, the object is an orphan that `scripts.cleanup_orphans` removes later. A row never points to
  an object that was not stored.
- Delete (of a file or of a record with attachments): the row first (commit), then the object. A failed
  object delete only leaves an orphan (logged), never a row without its object.

Records and attachments are linked without a FK (`files` is polymorphic). Uploads lock the record with
FOR KEY SHARE (the `exists_for_user` of each repository) just before inserting the row, and every module
deletes the record *before* its attachments, in the same transaction. So a delete running at the same
time as an upload either waits for the upload's commit (and then its DELETE on `files`, a later
statement, sees the new row) or commits first (and the upload gets "registro não encontrado").
"""

import logging
import uuid
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from typing import BinaryIO

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import NotFoundError, PayloadTooLargeError, ServiceUnavailableError, ValidationError
from app.core.file_types import (
    OCTET_STREAM,
    SECURITY_HEADERS,
    SNIFF_LENGTH,
    can_inline,
    content_disposition,
    sanitize_file_name,
    stored_content_type,
)
from app.core.storage import ObjectNotFound, ObjectReader, Storage, StorageError
from app.models import File
from app.models.file import FileEntityType
from app.repositories import file as file_repo
from app.repositories import pantry as pantry_repo
from app.repositories import pet as pet_repo
from app.repositories import routine as routine_repo
from app.repositories import shopping as shopping_repo
from app.repositories import task as task_repo
from app.repositories import transaction as transaction_repo
from app.schemas.file import FileCreate, FileQuery

logger = logging.getLogger(__name__)


class FileNotFound(NotFoundError):
    detail = "Arquivo não encontrado."


class StoredObjectMissing(NotFoundError):
    detail = "Arquivo não encontrado no armazenamento."


class EntityNotFound(ValidationError):
    detail = "Registro não encontrado para anexar."


class EmptyFile(ValidationError):
    detail = "O arquivo está vazio."


class FileTooLarge(PayloadTooLargeError):
    def __init__(self, max_mb: int) -> None:
        super().__init__(f"Arquivo maior que o limite de {max_mb} MB.")


class StorageUnavailable(ServiceUnavailableError):
    detail = "O armazenamento de arquivos está indisponível. Tente novamente."


# entity_type -> "does this record belong to the user?", each holding FOR KEY SHARE on the record.
EntityCheck = Callable[[Session, uuid.UUID, uuid.UUID], bool]
ENTITY_CHECKS: dict[str, EntityCheck] = {
    FileEntityType.TASK: task_repo.exists_for_user,
    FileEntityType.ROUTINE: routine_repo.exists_for_user,
    FileEntityType.PANTRY_ITEM: pantry_repo.exists_for_user,
    FileEntityType.SHOPPING_ITEM: shopping_repo.exists_for_user,
    FileEntityType.PET: pet_repo.exists_for_user,
    FileEntityType.PET_EVENT: pet_repo.event_exists_for_user,
    FileEntityType.TRANSACTION: transaction_repo.exists_for_user,
}


class _SizeLimitExceeded(Exception):
    pass


class _LimitedReader:
    """File-like wrapper that counts what the storage reads and stops past `limit` bytes.

    The size comes from this count, never from the request's Content-Length. `head` (bytes already read
    to detect the type) is returned first. `exceeded` stays True even if the storage library wraps the
    exception in one of its own.
    """

    def __init__(self, head: bytes, stream: BinaryIO, limit: int) -> None:
        self._head = head
        self._stream = stream
        self._limit = limit
        self.size = 0
        self.exceeded = False

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return False

    def read(self, size: int | None = -1) -> bytes:
        """Exactly `size` bytes, fewer only at the end: s3transfer takes a short read as the end of the
        stream (it would store a truncated object)."""
        if size is None or size < 0:
            # "Everything" is capped at one byte past the limit: enough to know it was exceeded.
            size = self._limit + 1 - self.size
        data, self._head = self._head[:size], self._head[size:]
        while len(data) < size:
            chunk = self._stream.read(size - len(data))
            if not chunk:
                break
            data += chunk
        self.size += len(data)
        if self.size > self._limit:
            self.exceeded = True
            raise _SizeLimitExceeded
        return data


def _require_entity(db: Session, user_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID) -> None:
    if not ENTITY_CHECKS[entity_type](db, user_id, entity_id):
        raise EntityNotFound


def purge_objects(storage: Storage, keys: Iterable[str]) -> None:
    """Delete objects whose rows are already gone (committed). Failures are only logged: what is left
    behind is an orphan that `scripts.cleanup_orphans` removes."""
    for key in keys:
        try:
            storage.delete(key)
        except Exception:
            logger.exception("Could not delete object %s from storage; cleanup_orphans will remove it", key)


def delete_attachments(
    db: Session, user_id: uuid.UUID, entity_type: FileEntityType, entity_ids: Iterable[uuid.UUID]
) -> list[str]:
    """Delete the rows of the records' attachments in the caller's transaction; returns the object keys.

    Call it after deleting the records themselves (module docstring), and pass the keys to
    `purge_objects` after the commit.
    """
    return file_repo.delete_for_entities(db, user_id, entity_type, list(entity_ids))


def get_file(db: Session, user_id: uuid.UUID, file_id: uuid.UUID, *, for_update: bool = False) -> File:
    """The user's file. Someone else's file is reported as missing (404), never as forbidden."""
    file = file_repo.get_for_user(db, user_id, file_id, for_update=for_update)
    if file is None:
        raise FileNotFound
    return file


def list_files(db: Session, user_id: uuid.UUID, query: FileQuery) -> list[File]:
    return file_repo.list_for_entity(db, user_id, query.entity_type, query.entity_id)


def upload_file(
    db: Session,
    storage: Storage,
    settings: Settings,
    user_id: uuid.UUID,
    data: FileCreate,
    stream: BinaryIO,
    file_name: str | None,
    declared_type: str | None,
) -> File:
    # Fail fast, before sending anything to the storage. The lock is released right away: no transaction
    # stays open while the object is uploaded. The check is repeated (and held) before the insert.
    _require_entity(db, user_id, data.entity_type, data.entity_id)
    db.rollback()

    head = stream.read(SNIFF_LENGTH)
    if not head:
        raise EmptyFile
    content_type = stored_content_type(head, declared_type)
    # No user input in the key: the original name only lives in the database.
    key = f"{user_id}/{data.entity_type}/{uuid.uuid4()}"
    reader = _LimitedReader(head, stream, settings.max_upload_bytes)
    try:
        storage.put(key, reader, content_type)
    except Exception as exc:
        purge_objects(storage, [key])  # a partial object (multipart) may have been left behind
        if reader.exceeded:
            raise FileTooLarge(settings.max_upload_mb) from None
        if isinstance(exc, StorageError):
            logger.exception("Upload of object %s failed", key)
            raise StorageUnavailable from exc
        raise

    try:
        _require_entity(db, user_id, data.entity_type, data.entity_id)
        file = File(
            user_id=user_id,
            entity_type=data.entity_type,
            entity_id=data.entity_id,
            bucket=storage.bucket,
            object_key=key,
            original_name=sanitize_file_name(file_name),
            content_type=content_type,
            size_bytes=reader.size,
        )
        file_repo.add(db, file)
        db.commit()
    except BaseException:
        db.rollback()
        purge_objects(storage, [key])
        raise
    return file


@dataclass(frozen=True)
class FileDownload:
    """What the router needs to stream the file: blocks, media type, headers and how to release the
    storage connection (`close`, idempotent: also when the client disconnects midway)."""

    chunks: Iterator[bytes]
    media_type: str
    headers: dict[str, str]
    close: Callable[[], None]


def _chunks(reader: ObjectReader, head: bytes, file_id: uuid.UUID) -> Iterator[bytes]:
    try:
        if head:
            yield head
        yield from reader.iter_chunks()
    except StorageError:
        # The status line is already sent: aborting is the only way to tell the client it is incomplete.
        logger.exception("Download of file %s was interrupted by the storage", file_id)
        raise
    finally:
        reader.close()


def open_download(
    db: Session, storage: Storage, user_id: uuid.UUID, file_id: uuid.UUID, *, inline: bool
) -> FileDownload:
    """Open the object for streaming. Inline only for safe types the bytes confirm (app.core.file_types)."""
    file = get_file(db, user_id, file_id)
    db.commit()  # end the read transaction now: the stream may take a while
    try:
        reader = storage.open(file.object_key)
    except ObjectNotFound:
        logger.error("File %s has no object %s in storage", file.id, file.object_key)
        raise StoredObjectMissing from None
    except StorageError as exc:
        logger.exception("Could not open object %s", file.object_key)
        raise StorageUnavailable from exc
    try:
        head = reader.read(SNIFF_LENGTH)
    except StorageError as exc:
        reader.close()
        logger.exception("Could not read object %s", file.object_key)
        raise StorageUnavailable from exc

    show_inline = inline and can_inline(file.content_type, head)
    headers = {
        **SECURITY_HEADERS,
        "Content-Disposition": content_disposition(file.original_name, inline=show_inline),
        # The object's real size, so a stream cut short is detectable by the client.
        "Content-Length": str(reader.size),
    }
    return FileDownload(
        chunks=_chunks(reader, head, file.id),
        media_type=file.content_type if show_inline else OCTET_STREAM,
        headers=headers,
        close=reader.close,
    )


def delete_file(db: Session, storage: Storage, user_id: uuid.UUID, file_id: uuid.UUID) -> None:
    file = get_file(db, user_id, file_id, for_update=True)
    key = file.object_key
    file_repo.delete(db, file)
    db.commit()
    purge_objects(storage, [key])
