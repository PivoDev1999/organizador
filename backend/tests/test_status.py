import json
import logging
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.request_id import RequestIdMiddleware
from app.core.logs import LogfmtFormatter
from app.core.system_status import (
    BACKUP_MAX_AGE_HOURS,
    BackupState,
    CheckStatus,
    Overall,
    evaluate_backup,
    evaluate_overall,
)

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
BACKUP_CORE = Path(__file__).resolve().parents[2] / "infra" / "backup" / "backuptool" / "core.py"


def _record(hours_ago: float) -> dict:
    return {"backup": "2026-10-29_030000", "finished_at": (NOW - timedelta(hours=hours_ago)).isoformat(),
            "size_bytes": 41418}  # fmt: skip


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        (_record(9), BackupState.OK),
        (_record(BACKUP_MAX_AGE_HOURS), BackupState.OK),  # the limit itself is still fresh
        (_record(BACKUP_MAX_AGE_HOURS + 0.1), BackupState.STALE),
        (None, BackupState.MISSING),
        ({"finished_at": "ontem"}, BackupState.UNREADABLE),
        ({"finished_at": "2026-10-29T03:00:00"}, BackupState.UNREADABLE),  # no time zone
    ],
)
def test_evaluate_backup(record, expected):
    info = evaluate_backup(record, NOW)

    assert info.status is expected
    if expected in (BackupState.OK, BackupState.STALE):
        assert info.name == "2026-10-29_030000"
        assert info.size_bytes == 41418


def test_backup_age_limit_matches_the_backup_service_healthcheck():
    assert BACKUP_CORE.is_file(), (
        f"{BACKUP_CORE} not found: where is MAX_AGE_HOURS of the backup service now?"
    )
    match = re.search(r"^MAX_AGE_HOURS\s*(:\s*\w+)?\s*=\s*([\d.]+)", BACKUP_CORE.read_text(), re.MULTILINE)
    assert match, f"MAX_AGE_HOURS not found in {BACKUP_CORE}"
    assert float(match[2]) == BACKUP_MAX_AGE_HOURS, "the backup healthcheck and GET /api/status disagree"


@pytest.mark.parametrize(
    ("database", "storage", "backup", "expected"),
    [
        (CheckStatus.OK, CheckStatus.OK, BackupState.OK, Overall.OK),
        (CheckStatus.OK, CheckStatus.UNAVAILABLE, BackupState.OK, Overall.DEGRADED),
        (CheckStatus.OK, CheckStatus.OK, BackupState.STALE, Overall.DEGRADED),
        (CheckStatus.OK, CheckStatus.OK, BackupState.MISSING, Overall.DEGRADED),
        (CheckStatus.UNAVAILABLE, CheckStatus.OK, BackupState.OK, Overall.DOWN),
    ],
)
def test_evaluate_overall(database, storage, backup, expected):
    assert evaluate_overall(database, storage, backup) is expected


def test_status_requires_login(client):
    assert client.get("/api/status").status_code == 401


def test_status_reports_storage_unavailable_without_failing(
    client, authenticate, storage, override_settings, tmp_path
):
    finished = datetime.now(UTC) - timedelta(hours=2)
    (tmp_path / "last_success.json").write_text(
        json.dumps({"backup": "2026-10-29_030000", "finished_at": finished.isoformat(), "size_bytes": 10})
    )
    override_settings(backups_dir=tmp_path)
    storage.fail_ping = True
    _, headers = authenticate()

    response = client.get("/api/status", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["storage"] == {"status": "unavailable", "latency_ms": None}
    assert body["database"]["status"] == "ok"
    assert body["database"]["alembic_revision"]
    assert body["backup"]["status"] == "ok"
    assert body["backup"]["max_age_hours"] == BACKUP_MAX_AGE_HOURS
    assert body["overall"] == "degraded"
    assert body["version"] == "dev"


def test_requests_get_an_id_and_the_access_log_has_no_query_string(client, caplog):
    with caplog.at_level(logging.INFO, logger="app.access"):
        generated = client.get("/api/tasks?q=segredo-pessoal")
        forwarded = client.get("/api/tasks", headers={"X-Request-ID": "0123456789abcdef0123456789abcdef"})
        forged = client.get("/api/tasks", headers={"X-Request-ID": 'x" level=ERROR'})

    assert re.fullmatch(r"[0-9a-f]{32}", generated.headers["X-Request-ID"])
    assert forwarded.headers["X-Request-ID"] == "0123456789abcdef0123456789abcdef"
    assert forged.headers["X-Request-ID"] != 'x" level=ERROR'

    access = [record for record in caplog.records if record.name == "app.access"]
    assert [(r.method, r.path, r.status) for r in access] == [("GET", "/api/tasks", 401)] * 3
    assert access[1].request_id == "0123456789abcdef0123456789abcdef"
    assert "segredo" not in caplog.text
    # Control characters never reach the terminal raw (ESC would start a terminal sequence).
    line = LogfmtFormatter().format(logging.makeLogRecord({"msg": "a\x1b[31mb\nc", "levelname": "INFO"}))
    assert 'msg="a\\x1b[31mb\\nc"' in line
    assert "\x1b" not in line


def test_unhandled_error_is_logged_and_answered_with_the_request_id(caplog):
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("falha inesperada")

    with caplog.at_level(logging.INFO):
        response = TestClient(app).get("/boom")

    assert response.status_code == 500
    assert response.json() == {"detail": "Erro interno."}
    request_id = response.headers["X-Request-ID"]
    errors = [LogfmtFormatter().format(r) for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert f"level=ERROR logger=app.errors request_id={request_id} " in errors[0]
    assert "RuntimeError: falha inesperada" in errors[0]
