import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser, SettingsDep, StorageDep
from app.api.responses import ClosingStreamingResponse
from app.core.database import DbSession
from app.schemas.file import FileCreate, FileDownloadQuery, FileEntityType, FileQuery, FileRead
from app.services import files as files_service

router = APIRouter(prefix="/files", tags=["files"])


@router.get("")
def list_files(
    query: Annotated[FileQuery, Query()], db: DbSession, current_user: CurrentUser
) -> list[FileRead]:
    """Anexos de um registro, do mais novo para o mais antigo."""
    return [FileRead.model_validate(file) for file in files_service.list_files(db, current_user.id, query)]


@router.post("", status_code=status.HTTP_201_CREATED)
def upload_file(
    entity_type: Annotated[FileEntityType, Form(description="Módulo do registro.")],
    entity_id: Annotated[uuid.UUID, Form(description="Id do registro (precisa ser seu).")],
    file: Annotated[UploadFile, File(description="O arquivo (qualquer tipo; limite em MAX_UPLOAD_MB).")],
    db: DbSession,
    storage: StorageDep,
    settings: SettingsDep,
    current_user: CurrentUser,
) -> FileRead:
    """Anexa um arquivo a um registro seu (multipart: `file`, `entity_type`, `entity_id`).

    O tipo guardado vem do conteúdo para JPEG, PNG, GIF, WebP e PDF; nos demais casos, do tipo
    informado (ou `application/octet-stream`). Arquivo vazio: 422. Acima do limite: 413.
    """
    # Separate Form params (not a Form model) so the OpenAPI documents multipart/form-data.
    data = FileCreate(entity_type=entity_type, entity_id=entity_id)
    created = files_service.upload_file(
        db, storage, settings, current_user.id, data, file.file, file.filename, file.content_type
    )
    return FileRead.model_validate(created)


@router.get("/{file_id}")
def get_file(file_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> FileRead:
    return FileRead.model_validate(files_service.get_file(db, current_user.id, file_id))


@router.get(
    "/{file_id}/download",
    response_class=StreamingResponse,
    responses={200: {"content": {"application/octet-stream": {}}, "description": "O conteúdo do arquivo."}},
)
def download_file(
    file_id: uuid.UUID,
    query: Annotated[FileDownloadQuery, Query()],
    db: DbSession,
    storage: StorageDep,
    current_user: CurrentUser,
) -> StreamingResponse:
    """Baixa o arquivo em streaming. Por padrão como anexo; `inline=true` só para tipos seguros."""
    download = files_service.open_download(db, storage, current_user.id, file_id, inline=query.inline)
    return ClosingStreamingResponse(
        download.chunks, close=download.close, media_type=download.media_type, headers=download.headers
    )


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(file_id: uuid.UUID, db: DbSession, storage: StorageDep, current_user: CurrentUser) -> None:
    files_service.delete_file(db, storage, current_user.id, file_id)
