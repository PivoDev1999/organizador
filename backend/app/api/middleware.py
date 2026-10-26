"""ASGI middlewares of the files API (pure ASGI, so streaming responses are not buffered)."""

from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings, get_settings
from app.core.file_types import SECURITY_HEADERS
from app.services.files import FileTooLarge

FILES_PATH = "/api/files"
# Room for the multipart envelope around the file (boundaries, part headers, the form fields): the
# exact file limit is enforced by the files service while it streams the file to the storage.
MULTIPART_OVERHEAD_BYTES = 1024 * 1024


def _is_files_path(path: str) -> bool:
    return path == FILES_PATH or path.startswith(FILES_PATH + "/")


def _settings(scope: Scope) -> Settings:
    # The same settings the routes get, so a test that overrides get_settings changes the limit here too.
    app = scope.get("app")
    overrides = getattr(app, "dependency_overrides", {})
    return overrides.get(get_settings, get_settings)()


class FilesSecurityHeaders:
    """Adds SECURITY_HEADERS (nosniff, CSP sandbox, no-store) to every response under /api/files: the
    downloads, but also their errors (401, 404, 413, 422, 503), which come from the same origin."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not _is_files_path(scope["path"]):
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    headers[name] = value
            await send(message)

        await self.app(scope, receive, send_with_headers)


class UploadBodyLimit:
    """Caps the request body of `POST /api/files` before Starlette spools the multipart to disk.

    - With Content-Length above the limit: 413 right away, without reading the body.
    - Without it (chunked) or with a body longer than declared: the bytes are counted as they arrive and
      the parse is aborted with 413 past the limit. The exception must be an HTTPException: FastAPI turns
      any other error raised while parsing the body into a 400. Starlette closes (deletes) the temporary
      files of an aborted parse.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"].rstrip("/") != FILES_PATH:
            await self.app(scope, receive, send)
            return

        settings = _settings(scope)
        limit = settings.max_upload_bytes + MULTIPART_OVERHEAD_BYTES
        detail = FileTooLarge(settings.max_upload_mb).detail
        declared = dict(scope["headers"]).get(b"content-length", b"")
        if declared.isdigit() and int(declared) > limit:
            response = JSONResponse({"detail": detail}, status_code=status.HTTP_413_CONTENT_TOO_LARGE)
            await response(scope, receive, send)
            return

        received = 0

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail=detail)
            return message

        await self.app(scope, counting_receive, send)
