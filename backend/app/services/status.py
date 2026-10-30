"""GET /api/status: version, uptime and the state of the database, the storage and the last backup.

Each check is isolated: a failure (or a timeout, see the probes) becomes "unavailable"/"unreadable" in its
own block and the endpoint still answers 200. The client gets only the status; the log gets the check
name and the exception class, never URLs, credentials or tracebacks.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import asdict

from sqlalchemy.orm import Session

from app.core import clock
from app.core.backups import BackupInfoUnreadable, read_last_success
from app.core.config import Settings
from app.core.storage import Storage
from app.core.system_status import (
    BACKUP_MAX_AGE_HOURS,
    BackupInfo,
    BackupState,
    CheckStatus,
    evaluate_backup,
    evaluate_overall,
    version_label,
)
from app.repositories import system as system_repository
from app.schemas.status import BackupStatusRead, DatabaseStatusRead, StorageStatusRead, SystemStatusRead

logger = logging.getLogger(__name__)

# Start of this process (each uvicorn worker has its own): the uptime counts from here.
_STARTED = time.monotonic()


class _Failed(Exception):
    """Marker: the probe raised (its exception was logged)."""


def _timed[T](check: str, probe: Callable[[], T]) -> tuple[T, float]:
    """Result of the probe and its latency in ms. Raises _Failed when the probe fails, whatever the error."""
    started = time.perf_counter()
    try:
        result = probe()
    except Exception as exc:  # isolation: any failure here only marks this check as unavailable
        # Only the class names (e.g. StorageError/EndpointConnectionError): never the message, which may
        # carry internal URLs.
        cause = f"/{type(exc.__cause__).__name__}" if exc.__cause__ else ""
        logger.warning("status check failed", extra={"check": check, "error": type(exc).__name__ + cause})
        raise _Failed from None
    return result, round((time.perf_counter() - started) * 1000, 1)


def check_database(db: Session) -> DatabaseStatusRead:
    try:
        revision, latency = _timed("database", lambda: system_repository.database_revision(db))
    except _Failed:
        db.rollback()  # close the failed transaction; the session is not used again in this request
        return DatabaseStatusRead(status=CheckStatus.UNAVAILABLE, latency_ms=None, alembic_revision=None)
    return DatabaseStatusRead(status=CheckStatus.OK, latency_ms=latency, alembic_revision=revision)


def check_storage(storage: Storage) -> StorageStatusRead:
    try:
        _, latency = _timed("storage", storage.ping)
    except _Failed:
        return StorageStatusRead(status=CheckStatus.UNAVAILABLE, latency_ms=None)
    return StorageStatusRead(status=CheckStatus.OK, latency_ms=latency)


def check_backup(settings: Settings) -> BackupInfo:
    try:
        record = read_last_success(settings.backups_dir)
    except BackupInfoUnreadable as exc:
        logger.warning("status check failed", extra={"check": "backup", "error": str(exc)})
        return BackupInfo(BackupState.UNREADABLE)
    info = evaluate_backup(record, clock.now_utc(), BACKUP_MAX_AGE_HOURS)
    if info.status is BackupState.UNREADABLE:
        logger.warning("status check failed", extra={"check": "backup", "error": "unexpected format"})
    return info


def get_system_status(db: Session, storage: Storage, settings: Settings) -> SystemStatusRead:
    """The checks run one after the other, each with its own timeout (database: statement_timeout of
    the probe; storage: PING_TIMEOUT_SECONDS, one attempt; backup: a local file)."""
    database = check_database(db)
    storage_status = check_storage(storage)
    backup = check_backup(settings)
    return SystemStatusRead(
        overall=evaluate_overall(database.status, storage_status.status, backup.status),
        version=version_label(settings.app_version, settings.git_sha),
        server_time=clock.now_utc().astimezone(settings.timezone),
        timezone=settings.app_timezone,
        uptime_seconds=int(time.monotonic() - _STARTED),
        database=database,
        storage=storage_status,
        backup=BackupStatusRead(**asdict(backup), max_age_hours=BACKUP_MAX_AGE_HOURS),
    )
