"""Guards the `client` fixture itself: uncommitted work must not survive the end of a request."""

from sqlalchemy.orm import Session

from tests.helpers import REGISTER_URL, login

USER = {"email": "esquecido@example.test", "name": "Sem Commit", "password": "senha-forte-123"}


def test_service_that_forgets_to_commit_is_caught(client, registration_open, monkeypatch):
    # Simulate a service without db.commit(): the insert is only flushed.
    monkeypatch.setattr(Session, "commit", Session.flush)

    assert client.post(REGISTER_URL, json=USER).status_code == 201

    monkeypatch.undo()
    assert login(client, USER["email"], USER["password"]).status_code == 401


def test_committed_work_survives_between_requests(client, registration_open):
    assert client.post(REGISTER_URL, json=USER).status_code == 201

    assert login(client, USER["email"], USER["password"]).status_code == 200
