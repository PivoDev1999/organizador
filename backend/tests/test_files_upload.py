import logging
import re
import uuid

import pytest
from sqlalchemy import func, select
from starlette.formparsers import MultiPartParser

from app.api.middleware import MULTIPART_OVERHEAD_BYTES
from app.models import File
from app.models.file import FileEntityType
from app.repositories import file as file_repo
from app.services import files as files_service
from tests.helpers import FILES_URL, HTML, PNG, assert_security_headers, upload

# Whole request body allowed with MAX_UPLOAD_MB=1: the file limit plus the multipart envelope.
MAX_1MB_BODY = 1024 * 1024 + MULTIPART_OVERHEAD_BYTES
KEY_PATTERN = r"{user}/task/[0-9a-f]{{8}}-[0-9a-f]{{4}}-4[0-9a-f]{{3}}-[0-9a-f]{{4}}-[0-9a-f]{{12}}"


@pytest.fixture
def ana(authenticate):
    return authenticate("ana@example.test")


@pytest.fixture
def task_id(ana, make_entity):
    return make_entity(ana[0], "task")


def _file_count(db_session) -> int:
    return db_session.scalar(select(func.count()).select_from(File))


def test_upload_stores_object_and_returns_file_read(client, ana, task_id, storage, db_session):
    user, headers = ana

    response = upload(client, headers, "task", task_id, PNG, "foto da nota.png", "image/png")

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == {
        "id",
        "entity_type",
        "entity_id",
        "original_name",
        "content_type",
        "size_bytes",
        "created_at",
    }
    assert body | {"id": None, "created_at": None} == {
        "id": None,
        "entity_type": "task",
        "entity_id": str(task_id),
        "original_name": "foto da nota.png",
        "content_type": "image/png",
        "size_bytes": len(PNG),
        "created_at": None,
    }
    row = db_session.get(File, uuid.UUID(body["id"]))
    # The key carries no user input (the file name lives only in the database).
    assert re.fullmatch(KEY_PATTERN.format(user=user.id), row.object_key)
    assert (row.bucket, row.user_id) == (storage.bucket, user.id)
    assert storage.objects == {row.object_key: PNG}


@pytest.mark.parametrize("entity_type", list(FileEntityType))
def test_upload_requires_an_existing_record_of_the_user(
    client, ana, authenticate, make_entity, storage, entity_type
):
    user, headers = ana
    bia, _ = authenticate("bia@example.test")

    own = upload(client, headers, entity_type, make_entity(user, entity_type))
    of_other_user = upload(client, headers, entity_type, make_entity(bia, entity_type))
    missing = upload(client, headers, entity_type, uuid.uuid4())

    assert own.status_code == 201, own.text
    for response in (of_other_user, missing):
        assert response.status_code == 422
        assert response.json()["detail"][0]["msg"] == "Registro não encontrado para anexar."
    assert len(storage.objects) == 1  # only the accepted upload reached the storage


def test_upload_above_the_limit_is_413_and_removes_the_partial_object(
    client, ana, task_id, storage, override_settings, db_session
):
    override_settings(max_upload_mb=1)
    storage.chunk_size = 256 * 1024  # several blocks get written before the limit is hit

    response = upload(client, ana[1], "task", task_id, PNG + b"\x00" * (1024 * 1024))

    assert response.status_code == 413
    assert response.json() == {"detail": "Arquivo maior que o limite de 1 MB."}
    assert len(storage.deleted) == 1
    assert storage.objects == {}
    assert _file_count(db_session) == 0


def test_upload_exactly_at_the_limit_is_accepted(client, ana, task_id, override_settings):
    override_settings(max_upload_mb=1)
    content = PNG + b"\x00" * (1024 * 1024 - len(PNG))

    response = upload(client, ana[1], "task", task_id, content)

    assert response.status_code == 201, response.text
    assert response.json()["size_bytes"] == 1024 * 1024


def test_empty_file_is_rejected_without_touching_the_storage(client, ana, task_id, storage):
    response = upload(client, ana[1], "task", task_id, b"", "vazio.txt", "text/plain")

    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == "O arquivo está vazio."
    assert storage.objects == {} and storage.deleted == []


@pytest.mark.parametrize(
    ("data", "with_file", "loc"),
    [
        ({"entity_type": "user", "entity_id": "TASK_ID"}, True, ["body", "entity_type"]),
        ({"entity_type": "task", "entity_id": "not-a-uuid"}, True, ["body", "entity_id"]),
        ({"entity_type": "task", "entity_id": "TASK_ID"}, False, ["body", "file"]),
    ],
    ids=["invalid-entity-type", "invalid-entity-id", "missing-file"],
)
def test_invalid_form_is_422(client, ana, task_id, storage, data, with_file, loc):
    data = {key: str(task_id) if value == "TASK_ID" else value for key, value in data.items()}
    files = {"file": ("a.png", PNG, "image/png")} if with_file else None

    response = client.post(FILES_URL, data=data, files=files, headers=ana[1])

    assert response.status_code == 422
    assert [error["loc"] for error in response.json()["detail"]] == [loc]
    assert storage.objects == {}


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", ""),
        ("get", "?entity_type=task&entity_id=00000000-0000-0000-0000-000000000000"),
        ("get", "/00000000-0000-0000-0000-000000000000"),
        ("get", "/00000000-0000-0000-0000-000000000000/download"),
        ("delete", "/00000000-0000-0000-0000-000000000000"),
    ],
    ids=["upload", "list", "get", "download", "delete"],
)
def test_every_endpoint_requires_authentication(client, method, path):
    response = client.request(method, FILES_URL + path)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert_security_headers(response)


def test_error_message_never_echoes_the_file_name(client, ana):
    response = upload(client, ana[1], "task", uuid.uuid4(), HTML, "segredo-<script>.html", "text/html")

    assert response.status_code == 422
    assert "segredo" not in response.text and "script" not in response.text


def test_failed_insert_after_put_removes_the_object(client, ana, task_id, storage, monkeypatch, caplog):
    def broken_add(db, file):
        raise RuntimeError("insert failed")

    monkeypatch.setattr(file_repo, "add", broken_add)

    assert upload(client, ana[1], "task", task_id).status_code == 500
    assert [str(r.exc_info[1]) for r in caplog.records if r.exc_info] == ["insert failed"]

    assert len(storage.deleted) == 1
    assert storage.objects == {}


def test_record_deleted_during_the_upload_is_422_and_removes_the_object(
    client, ana, task_id, storage, monkeypatch, db_session
):
    answers = iter([True, False])  # exists before the put, gone when the row is about to be inserted
    monkeypatch.setitem(
        files_service.ENTITY_CHECKS, FileEntityType.TASK, lambda db, user_id, id_: next(answers)
    )

    response = upload(client, ana[1], "task", task_id)

    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == "Registro não encontrado para anexar."
    assert storage.objects == {} and len(storage.deleted) == 1
    assert _file_count(db_session) == 0


def test_storage_failure_on_upload_is_503_and_logged(client, ana, task_id, storage, caplog, db_session):
    storage.fail_put = True

    with caplog.at_level(logging.ERROR, logger="app.services.files"):
        response = upload(client, ana[1], "task", task_id)

    assert response.status_code == 503
    assert response.json() == {"detail": "O armazenamento de arquivos está indisponível. Tente novamente."}
    assert "Upload of object" in caplog.text
    assert _file_count(db_session) == 0


@pytest.fixture
def endpoint_must_not_run(monkeypatch):
    """The body limit acts before the route: reaching the files service means it failed."""

    def reached(*args, **kwargs):
        raise AssertionError("the upload reached the service")

    monkeypatch.setattr(files_service, "upload_file", reached)


def test_content_length_above_the_limit_is_413_before_the_multipart_is_parsed(
    client, ana, task_id, override_settings, endpoint_must_not_run, monkeypatch
):
    override_settings(max_upload_mb=1)

    def parse(self):
        raise AssertionError("the multipart body was parsed (spooled to disk)")

    monkeypatch.setattr(MultiPartParser, "parse", parse)
    oversized = PNG + b"\x00" * (MAX_1MB_BODY + 1)

    response = upload(client, ana[1], "task", task_id, oversized)

    assert response.status_code == 413
    assert response.json() == {"detail": "Arquivo maior que o limite de 1 MB."}
    assert_security_headers(response)


def test_chunked_body_above_the_limit_is_413_while_it_arrives(
    client, ana, task_id, override_settings, endpoint_must_not_run
):
    override_settings(max_upload_mb=1)
    boundary = "limite"

    def body():
        yield (
            f'--{boundary}\r\nContent-Disposition: form-data; name="entity_type"\r\n\r\ntask\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="entity_id"\r\n\r\n{task_id}\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.bin"\r\n\r\n'
        ).encode()
        for _ in range(MAX_1MB_BODY // 65536 + 4):
            yield b"\x00" * 65536
        yield f"\r\n--{boundary}--\r\n".encode()

    response = client.post(
        FILES_URL,
        content=body(),
        headers={**ana[1], "Content-Type": f"multipart/form-data; boundary={boundary}"},
    )

    assert "content-length" not in response.request.headers
    assert response.status_code == 413
    assert response.json() == {"detail": "Arquivo maior que o limite de 1 MB."}
