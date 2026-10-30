"""Request id and access log of every HTTP request (pure ASGI, so streaming responses are not buffered).

- The id comes from the `X-Request-ID` header (Nginx sets it to its own `$request_id`, replacing whatever
  the client sent) or, without a valid one (development, direct calls), is generated here. It goes back in
  the `X-Request-ID` response header and on every log line of the request (app.core.logs).
- One `app.access` line per request: method, path, status and duration. Only the path: never the query
  string (it can carry personal data, e.g. a search), the body, the token or any header.
- An unhandled exception is logged here (level=ERROR, with the traceback and the request id) and answered
  with a generic 500 that also carries `X-Request-ID`, so the user's error can be found in the log. It is
  not re-raised: Starlette's ServerErrorMiddleware and uvicorn would log it again, without the id. If the
  response had already started (a download cut midway), nothing can be sent: it is logged and re-raised.
"""

import logging
import re
import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logs import request_id_var

HEADER = "X-Request-ID"
# Nginx's $request_id is 32 hex chars. Anything else from outside (too long, spaces, quotes) is replaced,
# so a client cannot forge log lines through this header.
_VALID_ID = re.compile(r"[A-Za-z0-9._-]{8,64}")
INTERNAL_ERROR = {"detail": "Erro interno."}
# Docker's healthcheck calls it every 15 s: successful calls are logged only at DEBUG.
QUIET_PATHS = frozenset({"/api/health"})

access_logger = logging.getLogger("app.access")
error_logger = logging.getLogger("app.errors")


def _incoming_id(scope: Scope) -> str | None:
    for name, value in scope["headers"]:
        if name == b"x-request-id":
            candidate = value.decode("latin-1")
            return candidate if _VALID_ID.fullmatch(candidate) else None
    return None


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _incoming_id(scope) or uuid.uuid4().hex
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status_code = 500
        started_response = False

        async def send_with_id(message: Message) -> None:
            nonlocal status_code, started_response
            if message["type"] == "http.response.start":
                status_code = message["status"]
                started_response = True
                MutableHeaders(scope=message)[HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception:
            if started_response:
                error_logger.warning("response interrupted", extra={"request_id": request_id}, exc_info=True)
                raise
            error_logger.exception("unhandled error", extra={"request_id": request_id})
            status_code = 500
            response = JSONResponse(INTERNAL_ERROR, status_code=500, headers={HEADER: request_id})
            await response(scope, receive, send)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            quiet = scope["path"] in QUIET_PATHS and status_code < 400
            access_logger.log(
                logging.DEBUG if quiet else logging.INFO,
                "request",
                extra={
                    "request_id": request_id,
                    "method": scope["method"],
                    "path": scope["path"],
                    "status": status_code,
                    "duration_ms": duration_ms,
                },
            )
            request_id_var.reset(token)
