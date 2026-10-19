import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.core.security import BCRYPT_MAX_BYTES
from app.schemas.common import DbText, Email, Utf8Str

NAME_MAX_LENGTH = 200
PASSWORD_MIN_LENGTH = 8


class UserCreate(BaseModel):
    email: Email
    name: DbText
    # Utf8Str, not DbText: the password only goes to bcrypt (which handles NUL), never to the database.
    password: Utf8Str

    @field_validator("name")
    @classmethod
    def _normalize_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Informe o nome.")
        if len(value) > NAME_MAX_LENGTH:
            raise ValueError(f"O nome deve ter no máximo {NAME_MAX_LENGTH} caracteres.")
        return value

    @field_validator("password")
    @classmethod
    def _check_password(cls, value: str) -> str:
        if len(value) < PASSWORD_MIN_LENGTH:
            raise ValueError(f"A senha deve ter pelo menos {PASSWORD_MIN_LENGTH} caracteres.")
        if len(value.encode()) > BCRYPT_MAX_BYTES:
            raise ValueError(
                f"A senha deve ter no máximo {BCRYPT_MAX_BYTES} bytes "
                "(letras acentuadas e emojis ocupam mais de um)."
            )
        return value


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str
    is_active: bool
    created_at: datetime
