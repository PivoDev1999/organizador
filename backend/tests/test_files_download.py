import logging
import uuid

import anyio
import pytest
from starlette.requests import ClientDisconnect

from app.main import app
from app.models import File
from tests.helpers import FILES_URL, GIF, HTML, JPEG, PDF, PNG, SVG, WEBP, assert_security_headers, upload

CSP = "default-src 'none'; sandbox"


@pytest.fixture
def ana(authenticate):
    return authenticate("ana@example.test")


@pytest.fixture
def task_id(ana, make_entity):
    return make_entity(ana[0], "task")


@pytest.fixture
def uploaded(client, ana, task_id):
    """upload(content, name, content_type) -> file id, attached to Ana's task."""

    def _upload(content: bytes = PNG, name: str = "foto.png", content_type: str | None = "image/png") -> str:
        response = upload(client, ana[1], "task", task_id, content, name, content_type)
        assert response.status_code == 201, response.text
        return response.json()["id"]

    return _upload


def _download(client, headers, file_id, inline: bool | None = None):
    params = {} if inline is None else {"inline": str(inline).lower()}
    return client.get(f"{FILES_URL}/{file_id}/download", params=params, headers=headers)


def test_default_download_is_an_attachment_streamed_in_blocks_with_security_headers(
    client, ana, uploaded, storage
):
    storage.chunk_size = 1000
    content = PNG + bytes(range(256)) * 20
    file_id = uploaded(content)

    response = _download(client, ana[1], file_id)

    assert response.status_code == 200
    assert response.content == content
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["content-disposition"].startswith('attachment; filename="foto.png"')
    assert response.headers["content-length"] == str(len(content))
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-security-policy"] == CSP
    assert response.headers["cache-control"] == "private, no-store"
    assert [reader.closed for reader in storage.readers] == [True]


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (JPEG, "image/jpeg"),
        (PNG, "image/png"),
        (GIF, "image/gif"),
        (WEBP, "image/webp"),
        (PDF, "application/pdf"),
    ],
    ids=["jpeg", "png", "gif", "webp", "pdf"],
)
def test_inline_uses_the_type_detected_from_the_bytes_not_the_declared_one(
    client, ana, uploaded, content, expected
):
    file_id = uploaded(content, "arquivo", "text/html")  # the client lies about the type

    response = _download(client, ana[1], file_id, inline=True)

    assert response.status_code == 200
    assert response.headers["content-type"] == expected
    assert response.headers["content-disposition"].startswith("inline;")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-security-policy"] == CSP


@pytest.mark.parametrize(
    ("content", "name", "declared"),
    [
        (HTML, "pagina.html", "image/png"),
        (SVG, "desenho.svg", "image/png"),
        (SVG, "desenho.svg", "image/svg+xml"),
    ],
    ids=["html-as-png", "svg-as-png", "svg"],
)
def test_unsafe_content_never_goes_inline(client, ana, uploaded, content, name, declared):
    file_id = uploaded(content, name, declared)

    response = _download(client, ana[1], file_id, inline=True)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.content == content


def test_stored_safe_type_whose_bytes_do_not_match_is_not_inline(client, ana, uploaded, db_session):
    file_id = uploaded(HTML, "pagina.html", "text/html")
    # A row that claims PNG for HTML bytes (edited by hand, an old import): the bytes decide.
    db_session.get(File, uuid.UUID(file_id)).content_type = "image/png"
    db_session.commit()

    response = _download(client, ana[1], file_id, inline=True)

    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["content-disposition"].startswith("attachment;")


def test_content_disposition_encodes_accented_names_with_ascii_fallback(client, ana, uploaded):
    file_id = uploaded(PDF, "Relatório de mães — 2026.pdf", "application/pdf")

    response = _download(client, ana[1], file_id)

    assert response.headers["content-disposition"] == (
        'attachment; filename="Relatorio de maes 2026.pdf"; '
        "filename*=UTF-8''Relat%C3%B3rio%20de%20m%C3%A3es%20%E2%80%94%202026.pdf"
    )


@pytest.mark.parametrize(
    ("stored_name", "fallback"),
    [
        ("../../etc/passwd", "_.._etc_passwd"),
        ('a"; filename="evil.html', "a__ filename__evil.html"),
        ("nota\r\nSet-Cookie: x=1.txt", "nota Set-Cookie_ x_1.txt"),
        ("文件.pdf", "arquivo.pdf"),
    ],
    ids=["path-traversal", "quotes", "crlf", "no-ascii-left"],
)
def test_content_disposition_neutralizes_malicious_names(
    client, ana, uploaded, db_session, stored_name, fallback
):
    # Straight into the row: the header must be safe even for names that did not pass the upload.
    file_id = uploaded()
    db_session.get(File, uuid.UUID(file_id)).original_name = stored_name
    db_session.commit()

    header = _download(client, ana[1], file_id).headers["content-disposition"]

    assert header.startswith(f"attachment; filename=\"{fallback}\"; filename*=UTF-8''")
    assert header.count('"') == 2
    assert "/" not in header and "\r" not in header and "\n" not in header


def test_object_missing_from_storage_is_404_and_logged(client, ana, uploaded, storage, caplog):
    file_id = uploaded()
    storage.objects.clear()

    with caplog.at_level(logging.ERROR, logger="app.services.files"):
        response = _download(client, ana[1], file_id)

    assert response.status_code == 404
    assert response.json() == {"detail": "Arquivo não encontrado no armazenamento."}
    assert f"File {file_id} has no object" in caplog.text
    assert_security_headers(response)


def test_unreachable_storage_on_download_is_503(client, ana, uploaded, storage):
    file_id = uploaded()
    storage.fail_open = True

    response = _download(client, ana[1], file_id)

    assert response.status_code == 503
    assert response.json() == {"detail": "O armazenamento de arquivos está indisponível. Tente novamente."}
    assert_security_headers(response)


def test_storage_reader_is_closed_when_the_client_disconnects_midway(client, ana, uploaded, storage):
    storage.chunk_size = 64
    file_id = uploaded(PNG + b"\x00" * 4096)
    bodies = []

    async def receive():
        await anyio.sleep_forever()

    async def send(message):
        if message["type"] == "http.response.body":
            bodies.append(message["body"])
            if len(bodies) == 2:
                raise OSError("connection reset by the client")

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": f"{FILES_URL}/{file_id}/download",
        "raw_path": f"{FILES_URL}/{file_id}/download".encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"testserver"), (b"authorization", ana[1]["Authorization"].encode())],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }

    async def disconnect_midway() -> list[bool]:
        with pytest.raises(ClientDisconnect):
            await app(scope, receive, send)
        # Checked while the event loop still runs, as in the server: ending the loop would finalize the
        # abandoned iterators and close the reader anyway.
        return [reader.closed for reader in storage.readers]

    closed = anyio.run(disconnect_midway)

    assert len(bodies) == 2  # stopped midway
    assert closed == [True]
