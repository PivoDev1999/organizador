from datetime import datetime

from pydantic import BaseModel

from app.core.system_status import BackupState, CheckStatus, Overall


class DatabaseStatusRead(BaseModel):
    status: CheckStatus
    # Round trip of the probe, in milliseconds; null when unavailable.
    latency_ms: float | None
    alembic_revision: str | None


class StorageStatusRead(BaseModel):
    status: CheckStatus
    latency_ms: float | None


class BackupStatusRead(BaseModel):
    status: BackupState
    last_success_at: datetime | None
    age_hours: float | None
    size_bytes: int | None
    # Directory of the backup inside backups/ (e.g. 2026-10-28_030000).
    name: str | None
    # Above this age the backup is "stale" (the same limit as the healthcheck of the backup service).
    max_age_hours: int


class SystemStatusRead(BaseModel):
    overall: Overall
    version: str
    server_time: datetime
    timezone: str
    uptime_seconds: int
    database: DatabaseStatusRead
    storage: StorageStatusRead
    backup: BackupStatusRead
