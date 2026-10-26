from datetime import timedelta

import pytest

from app.core import clock
from app.models import File
from scripts.cleanup_orphans import MIN_AGE, cleanup_orphans
from tests.fakes import FakeStorage


@pytest.fixture
def ana(create_user):
    return create_user("ana@example.test")


@pytest.fixture
def scenario(ana, make_entity, storage, db_session):
    """Two referenced objects, an old orphan, a recent orphan (upload in progress) and a row whose
    object is gone."""
    now = clock.now_utc()
    task = make_entity(ana, "task")
    rows = []
    for name in ("kept", "lost"):
        key = f"{ana.id}/task/{name}"
        row = File(
            user_id=ana.id,
            entity_type="task",
            entity_id=task,
            bucket=storage.bucket,
            object_key=key,
            original_name=f"{name}.txt",
            content_type="text/plain",
            size_bytes=1,
        )
        rows.append(row)
        storage.objects[key], storage.modified[key] = b"x", now - timedelta(days=3)
    # Same key in another bucket: does not make the fake bucket's object referenced.
    db_session.add_all(
        [*rows, File(**{**_columns(rows[0]), "bucket": "other", "object_key": "x/orphan-old"})]
    )
    db_session.commit()
    del storage.objects[rows[1].object_key]
    storage.objects["x/orphan-old"], storage.modified["x/orphan-old"] = b"o", now - MIN_AGE - timedelta(1)
    storage.objects["x/orphan-new"], storage.modified["x/orphan-new"] = (
        b"n",
        now - MIN_AGE + timedelta(minutes=5),
    )
    return now, rows


def _columns(row: File) -> dict:
    names = ("user_id", "entity_type", "entity_id", "original_name", "content_type", "size_bytes")
    return {name: getattr(row, name) for name in names}


def test_cleanup_deletes_old_orphans_keeps_recent_ones_and_reports_rows_without_object(
    scenario, storage, db_session
):
    now, (kept, lost) = scenario

    report = cleanup_orphans(db_session, storage, now=now)

    assert report.deleted == ["x/orphan-old"]
    assert report.kept_recent == ["x/orphan-new"]
    assert report.rows_without_object == [lost.id]
    assert report.failed == []
    assert sorted(storage.objects) == sorted([kept.object_key, "x/orphan-new"])
    assert db_session.get(File, lost.id) is not None  # reported, never deleted


def test_dry_run_reports_without_deleting(scenario, storage, db_session):
    now, _ = scenario
    before = dict(storage.objects)

    report = cleanup_orphans(db_session, storage, now=now, dry_run=True)

    assert report.deleted == ["x/orphan-old"]
    assert storage.objects == before and storage.deleted == []


def test_objects_that_fail_to_delete_are_reported(scenario, storage: FakeStorage, db_session):
    now, _ = scenario
    storage.fail_delete = True

    report = cleanup_orphans(db_session, storage, now=now)

    assert (report.deleted, report.failed) == ([], ["x/orphan-old"])
