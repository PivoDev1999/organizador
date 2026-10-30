"""Pure rules of GET /api/status: backup freshness, overall status and the version label. No I/O, no clock.

`app.services.status` gathers the facts (database, storage, backups/last_success.json) and asks these
functions what they mean, so the rules are tested without any of those services.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

# Same limit as the healthcheck of the `backup` service (MAX_AGE_HOURS in infra/backup/backuptool/core.py):
# the two images do not share code, so both constants must change together (tests/test_status.py checks).
BACKUP_MAX_AGE_HOURS = 26

DEV_VERSION = "dev"


class CheckStatus(StrEnum):
    OK = "ok"
    UNAVAILABLE = "unavailable"


class BackupState(StrEnum):
    OK = "ok"
    STALE = "stale"  # the last successful backup is older than BACKUP_MAX_AGE_HOURS
    MISSING = "missing"  # no last_success.json: no backup ever finished
    UNREADABLE = "unreadable"  # the file exists but cannot be read or is not in the expected format


class Overall(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    DOWN = "down"


@dataclass(frozen=True)
class BackupInfo:
    status: BackupState
    last_success_at: datetime | None = None
    age_hours: float | None = None
    size_bytes: int | None = None
    name: str | None = None


def evaluate_backup(
    record: object | None, now: datetime, max_age_hours: float = BACKUP_MAX_AGE_HOURS
) -> BackupInfo:
    """What last_success.json (already parsed, or None when the file does not exist) says about the backup.

    `finished_at` must be an ISO 8601 timestamp with a time zone (the format the backup service writes).
    The age is never negative: a timestamp slightly in the future (clocks apart) counts as just finished.
    """
    if record is None:
        return BackupInfo(BackupState.MISSING)
    if not isinstance(record, Mapping):
        return BackupInfo(BackupState.UNREADABLE)
    try:
        finished = datetime.fromisoformat(record["finished_at"])
    except (KeyError, TypeError, ValueError):
        return BackupInfo(BackupState.UNREADABLE)
    if finished.tzinfo is None:
        return BackupInfo(BackupState.UNREADABLE)

    age_hours = max((now - finished).total_seconds() / 3600, 0.0)
    size = record.get("size_bytes")
    name = record.get("backup")
    return BackupInfo(
        status=BackupState.STALE if age_hours > max_age_hours else BackupState.OK,
        last_success_at=finished,
        age_hours=round(age_hours, 2),
        size_bytes=size if isinstance(size, int) and not isinstance(size, bool) else None,
        name=name if isinstance(name, str) else None,
    )


def evaluate_overall(database: CheckStatus, storage: CheckStatus, backup: BackupState) -> Overall:
    """- down: the database is unavailable (nothing in the app works without it);
    - degraded: the app works, but something needs attention: attachments unavailable (storage) or the
      data unprotected (backup stale, missing or unreadable);
    - ok: everything else."""
    if database is not CheckStatus.OK:
        return Overall.DOWN
    if storage is not CheckStatus.OK or backup is not BackupState.OK:
        return Overall.DEGRADED
    return Overall.OK


def version_label(app_version: str, git_sha: str) -> str:
    """Version label: "1.2.0+abc1234" with both, either one alone, "dev" with neither (development, CI)."""
    parts = [part.strip() for part in (app_version, git_sha) if part.strip() and part.strip() != DEV_VERSION]
    return "+".join(parts) if parts else DEV_VERSION
