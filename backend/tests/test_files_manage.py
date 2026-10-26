import logging
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models import File
from tests.helpers import FILES_URL, PNG, upload


@pytest.fixture
def ana(authenticate):
    return authenticate("ana@example.test")


@pytest.fixture
def bia(authenticate):
    return authenticate("bia@example.test")


def test_list_returns_only_the_attachments_of_that_record_newest_first(
    client, ana, bia, make_entity, db_session
):
    (user, headers), (other, other_headers) = ana, bia
    task, other_task, pet = (make_entity(user, "task"), make_entity(user, "task"), make_entity(user, "pet"))
    ids = [upload(client, headers, "task", task, name=f"{n}.png").json()["id"] for n in range(3)]
    upload(client, headers, "task", other_task)
    upload(client, headers, "pet", pet)
    upload(client, other_headers, "task", make_entity(other, "task"))
    # Same transaction, same now(): spread created_at so the order is visible (ids[1] and ids[2] tie).
    for file_id, day in zip(ids, (1, 2, 2), strict=True):
        db_session.get(File, uuid.UUID(file_id)).created_at = datetime(2026, 1, day, tzinfo=UTC)
    db_session.commit()

    response = client.get(FILES_URL, params={"entity_type": "task", "entity_id": str(task)}, headers=headers)

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [*sorted(ids[1:]), ids[0]]
    assert [item["original_name"] for item in response.json()][-1] == "0.png"


@pytest.mark.parametrize("missing", ["entity_type", "entity_id"])
def test_list_requires_both_query_params(client, ana, missing):
    params = {"entity_type": "task", "entity_id": str(uuid.uuid4())}
    del params[missing]

    response = client.get(FILES_URL, params=params, headers=ana[1])

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", missing]


def test_get_returns_the_file(client, ana, make_entity):
    task = make_entity(ana[0], "task")
    created = upload(client, ana[1], "task", task).json()

    response = client.get(f"{FILES_URL}/{created['id']}", headers=ana[1])

    assert response.status_code == 200
    assert response.json() == created


@pytest.mark.parametrize(
    ("method", "suffix"),
    [("get", ""), ("get", "/download"), ("delete", "")],
    ids=["get", "download", "delete"],
)
def test_file_of_another_user_is_not_found_and_kept(
    client, ana, bia, make_entity, storage, db_session, method, suffix
):
    other, other_headers = bia
    file_id = upload(client, other_headers, "task", make_entity(other, "task")).json()["id"]

    response = client.request(method, f"{FILES_URL}/{file_id}{suffix}", headers=ana[1])

    assert response.status_code == 404
    assert response.json() == {"detail": "Arquivo não encontrado."}
    assert db_session.get(File, uuid.UUID(file_id)) is not None
    assert list(storage.objects.values()) == [PNG]


def test_delete_removes_row_and_object(client, ana, make_entity, storage, db_session):
    file_id = upload(client, ana[1], "task", make_entity(ana[0], "task")).json()["id"]

    response = client.delete(f"{FILES_URL}/{file_id}", headers=ana[1])

    assert response.status_code == 204
    assert db_session.get(File, uuid.UUID(file_id)) is None
    assert storage.objects == {} and len(storage.deleted) == 1
    assert client.get(f"{FILES_URL}/{file_id}", headers=ana[1]).status_code == 404


def test_delete_with_storage_failing_is_still_204_and_logs_the_orphan(
    client, ana, make_entity, storage, db_session, caplog
):
    file_id = upload(client, ana[1], "task", make_entity(ana[0], "task")).json()["id"]
    key = db_session.scalar(select(File.object_key).where(File.id == uuid.UUID(file_id)))
    storage.fail_delete = True

    with caplog.at_level(logging.ERROR, logger="app.services.files"):
        response = client.delete(f"{FILES_URL}/{file_id}", headers=ana[1])

    assert response.status_code == 204
    assert db_session.get(File, uuid.UUID(file_id)) is None
    assert key in storage.objects  # the orphan stays until scripts.cleanup_orphans runs
    assert f"Could not delete object {key}" in caplog.text
