"""Logging of the API: one line per event, in logfmt (`key=value`), with the request id of each request.

Why logfmt and not JSON: the logs are read by a person with `docker compose logs` (there is no log
collector on the home server), and logfmt stays readable in a terminal while still being easy to filter
with grep (`grep request_id=<id>`). The Nginx access log (frontend/nginx/nginx.conf) uses the same style,
so one request can be followed from the proxy to the API with the same filter.

Example:
    time=2026-10-29T10:15:02.123-03:00 level=INFO logger=app.access request_id=4f2c... msg="request"
    method=GET path=/api/status status=200 duration_ms=12.4

Values with spaces, quotes, "=" or control characters are quoted; line breaks (tracebacks included) are
escaped as "\\n" (also "\\r", "\\t"), every other control character as "\\xNN" (ESC: "\\x1b"), so every event
stays on one line and no terminal sequence reaches `docker compose logs`.
"""

import logging
import logging.config
import re
from contextvars import ContextVar
from datetime import datetime

# Request id of the request being handled (set by app.api.request_id.RequestIdMiddleware).
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_BARE_VALUE = re.compile(r"[^\s\"=\\\x00-\x1f\x7f]+")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_SHORT_ESCAPES = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}
# Standard LogRecord attributes: everything else in record.__dict__ came from `extra=` and is printed.
# color_message: uvicorn's copy of the message with terminal colors.
_RESERVED = frozenset(logging.makeLogRecord({}).__dict__) | {
    "message",
    "asctime",
    "request_id",
    "color_message",
}


def _quote(value: object) -> str:
    text = str(value)
    if text and _BARE_VALUE.fullmatch(text):
        return text
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    # Every control character is escaped (ESC included): no terminal sequences in `docker compose logs`.
    escaped = _CONTROL.sub(lambda m: _SHORT_ESCAPES.get(m[0], f"\\x{ord(m[0]):02x}"), escaped)
    return f'"{escaped}"'


class RequestIdFilter(logging.Filter):
    """Adds `record.request_id` ("-" outside a request) to every record that goes through the handler."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = request_id_var.get()
        return True


class LogfmtFormatter(logging.Formatter):
    """time, level, logger, request_id and msg, then the `extra=` fields in the order they were given."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created).astimezone()
        fields: list[tuple[str, object]] = [
            ("time", timestamp.isoformat(timespec="milliseconds")),
            ("level", record.levelname),
            ("logger", record.name),
            ("request_id", getattr(record, "request_id", request_id_var.get())),
            ("msg", record.getMessage()),
        ]
        fields += [(key, value) for key, value in record.__dict__.items() if key not in _RESERVED]
        if record.exc_info:
            fields.append(("exc", self.formatException(record.exc_info)))
        return " ".join(f"{key}={_quote(value)}" for key, value in fields)


# Also the --log-config of uvicorn in the container (docker-entrypoint.sh writes it to /tmp from this
# dict), so the parent process and every worker log the same way. uvicorn.access is silenced: app.access
# (app.api.request_id) replaces it, with the request id and without the query string.
LOGGING_CONFIG: dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_id": {"()": "app.core.logs.RequestIdFilter"}},
    "formatters": {"logfmt": {"()": "app.core.logs.LogfmtFormatter"}},
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "logfmt",
            "filters": ["request_id"],
        }
    },
    "root": {"level": "INFO", "handlers": ["stdout"]},
    "loggers": {
        "uvicorn": {"level": "INFO", "handlers": [], "propagate": True},
        "uvicorn.error": {"level": "INFO", "handlers": [], "propagate": True},
        "uvicorn.access": {"level": "WARNING", "handlers": [], "propagate": False},
    },
}


def configure_logging() -> None:
    """Idempotent. In the container uvicorn already applied the same config (--log-config); in
    development (`uvicorn --reload`) this replaces uvicorn's default format with ours."""
    root = logging.getLogger()
    if any(isinstance(handler.formatter, LogfmtFormatter) for handler in root.handlers):
        return
    logging.config.dictConfig(LOGGING_CONFIG)
