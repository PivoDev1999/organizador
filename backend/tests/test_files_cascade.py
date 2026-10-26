"""Deleting a record deletes its attachments: rows in the same transaction, objects after the commit."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models import File
from app.models.file import FileEntityType
from tests.helpers import upload

DELETE_URLS = {
    FileEntityType.TASK: "/api/tasks/{id}",
    FileEntityType.ROUTINE: "/api/routines/{id}",
    FileEntityType.PANTRY_ITEM: "/api/pantry/{id}",
    FileEntityType.SHOPPING_ITEM: "/api/shopping/{id}",
    FileEntityType.PET: "/api/pets/{id}",
    FileEntityType.PET_EVENT: "/api/pets/{pet_id}/events/{id}",
    FileEntityType.TRANSACTION: "/api/transactions/{id}",
}


@pytest.fixture
def ana(authenticate):
    return authenticate("ana@example.test")


def _attach(client, headers, entity_type, entity_id, count: int = 1) -> list[str]:
    ids = []
    for _ in range(count):
        response = upload(client, headers, entity_type, entity_id)
        assert response.status_code == 201, response.text
        ids.append(response.json()["id"])
    return ids


def _remaining(db_session) -> set[str]:
    return {str(file_id) for file_id in db_session.scalars(select(File.id))}


def _keys(db_session) -> set[str]:
    return set(db_session.scalars(select(File.object_key)))


@pytest.mark.parametrize("entity_type", list(FileEntityType))
def test_deleting_a_record_deletes_its_attachments_and_objects(
    client, ana, make_entity, storage, db_session, entity_type
):
    user, headers = ana
    pet_id = make_entity(user, "pet")
    extra = {"pet_id": pet_id} if entity_type == FileEntityType.PET_EVENT else {}
    target, kept = make_entity(user, entity_type, **extra), make_entity(user, entity_type, **extra)
    _attach(client, headers, entity_type, target, count=2)
    kept_ids = _attach(client, headers, entity_type, kept)

    url = DELETE_URLS[entity_type].format(id=target, pet_id=pet_id)
    response = client.delete(url, headers=headers)

    assert response.status_code == 204, response.text
    assert _remaining(db_session) == set(kept_ids)
    assert set(storage.objects) == _keys(db_session)
    assert len(storage.deleted) == 2


def test_deleting_a_pet_deletes_the_attachments_of_all_its_events(
    client, ana, make_entity, storage, db_session
):
    user, headers = ana
    pet, other_pet = make_entity(user, "pet"), make_entity(user, "pet")
    _attach(client, headers, "pet", pet)
    for _ in range(2):
        _attach(client, headers, "pet_event", make_entity(user, "pet_event", pet_id=pet), count=2)
    kept = _attach(client, headers, "pet_event", make_entity(user, "pet_event", pet_id=other_pet))
    expense = make_entity(user, "transaction", pet_id=pet)
    kept += _attach(client, headers, "transaction", expense)  # the expense survives (pet_id SET NULL)

    response = client.delete(f"/api/pets/{pet}", headers=headers)

    assert response.status_code == 204
    assert _remaining(db_session) == set(kept)
    assert set(storage.objects) == _keys(db_session)
    assert len(storage.deleted) == 5


def test_deleting_purchased_items_deletes_their_attachments(client, ana, make_entity, storage, db_session):
    user, headers = ana
    for _ in range(2):
        _attach(
            client,
            headers,
            "shopping_item",
            make_entity(user, "shopping_item", is_purchased=True, purchased_at=datetime.now(UTC)),
        )
    kept = _attach(client, headers, "shopping_item", make_entity(user, "shopping_item"))

    response = client.delete("/api/shopping/purchased", headers=headers)

    assert response.status_code == 204
    assert _remaining(db_session) == set(kept)
    assert set(storage.objects) == _keys(db_session)
    assert len(storage.deleted) == 2
