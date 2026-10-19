import uuid
from enum import StrEnum

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, EntityMixin, in_check


class FileEntityType(StrEnum):
    TASK = "task"
    ROUTINE = "routine"
    PANTRY_ITEM = "pantry_item"
    SHOPPING_ITEM = "shopping_item"
    PET = "pet"
    PET_EVENT = "pet_event"
    TRANSACTION = "transaction"


class File(EntityMixin, Base):
    """Metadata of an object stored in S3. Polymorphic: (entity_type, entity_id) points to any module,
    so there is no FK on entity_id and the service layer must clean up files of deleted entities."""

    __tablename__ = "files"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    entity_type: Mapped[str] = mapped_column(String(20))
    entity_id: Mapped[uuid.UUID]
    bucket: Mapped[str] = mapped_column(String(63))
    object_key: Mapped[str] = mapped_column(String(1024))
    original_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(BigInteger)

    __table_args__ = (
        CheckConstraint(in_check("entity_type", FileEntityType), name="entity_type"),
        CheckConstraint("size_bytes >= 0", name="size_bytes_non_negative"),
        Index("ix_files_entity_type_entity_id", "entity_type", "entity_id"),
        UniqueConstraint("bucket", "object_key"),
    )
