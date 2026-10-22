import uuid
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import DateTime, FetchedValue, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Deterministic constraint names keep Alembic migrations stable and reviewable.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    # Every timestamp in the project is timezone-aware (timestamptz).
    type_annotation_map = {datetime: DateTime(timezone=True)}


class EntityMixin:
    """UUID primary key plus created/updated timestamps, shared by every table."""

    # Fetch server-generated values (updated_at from the trigger) with RETURNING in the same statement,
    # instead of a lazy SELECT after commit that fails if the row was deleted meanwhile.
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=func.gen_random_uuid(), sort_order=-100
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), sort_order=100)
    # Maintained by the set_updated_at() trigger, so raw SQL updates are covered too.
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), server_onupdate=FetchedValue(), sort_order=100
    )


def in_check(column: str, values: Iterable[str]) -> str:
    """SQL for a CHECK that emulates an enum on a VARCHAR column."""
    options = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({options})"
