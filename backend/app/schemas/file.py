import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.file import FileEntityType


class FileCreate(BaseModel):
    """Record an upload is attached to (form fields of `POST /api/files`, besides the `file` itself)."""

    model_config = ConfigDict(use_enum_values=True)

    entity_type: FileEntityType = Field(description="Módulo do registro ao qual o arquivo é anexado.")
    entity_id: uuid.UUID = Field(description="Id do registro (precisa ser seu).")


class FileQuery(BaseModel):
    """Query string of `GET /api/files`: the record whose attachments are listed. Both are required."""

    model_config = ConfigDict(use_enum_values=True)

    entity_type: FileEntityType
    entity_id: uuid.UUID


class FileDownloadQuery(BaseModel):
    inline: bool = Field(
        default=False,
        description=(
            "true: exibir no navegador, permitido só para JPEG, PNG, GIF, WebP e PDF confirmados pelo "
            "conteúdo. Nos demais casos o arquivo sempre vem como download (application/octet-stream)."
        ),
    )


class FileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type: FileEntityType
    entity_id: uuid.UUID
    original_name: str
    content_type: str
    size_bytes: int
    created_at: datetime
