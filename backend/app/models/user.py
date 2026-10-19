from sqlalchemy import Index, String, func, true
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, EntityMixin

EMAIL_UNIQUE_INDEX = "uq_users_email_lower"


class User(EntityMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(server_default=true())

    __table_args__ = (
        # Case-insensitive uniqueness: "Ana@x.com" and "ana@x.com" are the same account.
        Index(EMAIL_UNIQUE_INDEX, func.lower(email), unique=True),
    )
