import uuid

import bcrypt
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.security import DEFAULT_BCRYPT_ROUNDS, verify_password
from app.models import User
from app.repositories import user as user_repo
from app.repositories.errors import DuplicateError
from app.schemas.user import UserCreate
from app.services import auth as auth_service
from tests.helpers import (
    REGISTER_URL,
    login,
    make_settings,
)

NEW_USER = {"email": "  Bruno@Example.TEST ", "name": "  Bruno   Silva ", "password": "senha-forte-123"}


def test_register_creates_user_with_normalized_fields(client, db_session, registration_open):
    response = client.post(REGISTER_URL, json=NEW_USER)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "email", "name", "is_active", "created_at"}
    assert body["email"] == "bruno@example.test"
    assert body["name"] == "Bruno Silva"
    assert body["is_active"] is True

    user = db_session.get(User, uuid.UUID(body["id"]))
    assert verify_password(NEW_USER["password"], user.password_hash)


def test_register_is_forbidden_when_registration_is_disabled(client, db_session, override_settings):
    override_settings(allow_registration=False)

    response = client.post(REGISTER_URL, json=NEW_USER)

    assert response.status_code == 403
    assert response.json()["detail"] == "Cadastro desabilitado."
    assert db_session.scalar(select(func.count()).select_from(User).where(User.email.ilike("bruno@%"))) == 0


def test_register_rejects_duplicate_email_case_insensitive(client, create_user, registration_open):
    create_user(email="bruno@example.test")

    response = client.post(REGISTER_URL, json=NEW_USER)

    assert response.status_code == 409
    assert response.json()["detail"] == "E-mail já cadastrado."


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("email", "sem-arroba.example.test", "E-mail inválido."),
        ("email", "a b@example.test", "E-mail inválido."),
        ("name", "   ", "Informe o nome."),
        ("password", "curta", "pelo menos 8 caracteres"),
        ("password", "á" * 37, "no máximo 72 bytes"),
    ],
)
def test_register_validates_payload(client, registration_open, field, value, message):
    response = client.post(REGISTER_URL, json={**NEW_USER, field: value})

    assert response.status_code == 422
    errors = response.json()["detail"]
    assert errors[0]["loc"] == ["body", field]
    assert message in errors[0]["msg"]


def test_register_accepts_password_of_exactly_72_bytes(client, registration_open):
    response = client.post(REGISTER_URL, json={**NEW_USER, "password": "á" * 36})

    assert response.status_code == 201


def test_register_race_on_unique_index_becomes_email_already_registered(db_session, create_user, monkeypatch):
    create_user(email="bruno@example.test")  # committed, as by the concurrent request
    # Simulate the concurrent request winning between the existence check and the insert.
    monkeypatch.setattr(user_repo, "get_by_email", lambda db, email: None)
    settings = make_settings(allow_registration=True)

    with pytest.raises(auth_service.EmailAlreadyRegistered) as exc_info:
        auth_service.register(db_session, settings, UserCreate(**NEW_USER))

    assert isinstance(exc_info.value.__cause__, DuplicateError)
    assert isinstance(exc_info.value.__cause__.__cause__, IntegrityError)
    # The session is still usable after the rollback.
    assert db_session.scalar(select(func.count()).select_from(User).where(User.email.ilike("bruno@%"))) == 1


@pytest.mark.parametrize(
    ("name", "stored"),
    [
        ("José da Conceição", "José da Conceição"),
        ("山田 太郎", "山田 太郎"),
        ("Zoë 😀", "Zoë 😀"),
        ("Ana\tMaria\nSouza", "Ana Maria Souza"),
    ],
    ids=["accents", "cjk", "emoji", "tabs-and-newlines"],
)
def test_register_accepts_unicode_names(client, db_session, registration_open, name, stored):
    response = client.post(REGISTER_URL, json={**NEW_USER, "name": name})

    assert response.status_code == 201
    assert response.json()["name"] == stored
    assert db_session.get(User, uuid.UUID(response.json()["id"])).name == stored


@pytest.mark.parametrize(
    "name", ["", "   ", "\t\n", "\u3000"], ids=["empty", "spaces", "tab-newline", "ideographic-space"]
)
def test_register_rejects_blank_name(client, registration_open, name):
    response = client.post(REGISTER_URL, json={**NEW_USER, "name": name})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "name"]


def test_register_name_length_limit(client, registration_open):
    assert client.post(REGISTER_URL, json={**NEW_USER, "name": "a" * 200}).status_code == 201

    response = client.post(REGISTER_URL, json={**NEW_USER, "email": "outro@example.test", "name": "a" * 201})
    assert response.status_code == 422
    assert "no máximo 200 caracteres" in response.json()["detail"][0]["msg"]


@pytest.mark.parametrize(
    "email",
    [
        "",
        "ana@",
        "@example.test",
        "ana@example",
        "ana@@example.test",
        "ana@b@example.test",
        "ana maria@example.test",
        "ana@exa mple.test",
        "a" * 243 + "@example.test",
    ],
    ids=[
        "empty",
        "no-domain",
        "no-local-part",
        "domain-without-dot",
        "double-at",
        "two-ats",
        "space-in-local-part",
        "space-in-domain",
        "256-chars",
    ],
)
def test_register_rejects_invalid_email(client, registration_open, email):
    response = client.post(REGISTER_URL, json={**NEW_USER, "email": email})

    assert response.status_code == 422
    errors = response.json()["detail"]
    assert errors[0]["loc"] == ["body", "email"]
    assert "E-mail inválido." in errors[0]["msg"]


def test_register_accepts_email_of_exactly_255_chars(client, registration_open):
    email = "a" * 242 + "@example.test"
    assert len(email) == 255

    response = client.post(REGISTER_URL, json={**NEW_USER, "email": email})

    assert response.status_code == 201
    assert response.json()["email"] == email


def test_register_length_limit_applies_after_trimming_email(client, registration_open):
    email = "  " + "a" * 242 + "@example.test  "

    response = client.post(REGISTER_URL, json={**NEW_USER, "email": email})

    assert response.status_code == 201


@pytest.mark.parametrize(
    ("password", "accepted"),
    [
        ("1234567", False),
        ("12345678", True),
        ("áéíóúãõ", False),  # 7 characters, 14 bytes: the minimum counts characters
        ("áéíóúãõç", True),
        ("a" * 72, True),
        ("a" * 73, False),
        ("😀" * 18, True),  # 72 bytes
        ("😀" * 19, False),  # 76 bytes
        ("a" + "á" * 36, False),  # 73 bytes
    ],
    ids=[
        "7-chars",
        "8-chars",
        "7-multibyte-chars",
        "8-multibyte-chars",
        "72-ascii-bytes",
        "73-ascii-bytes",
        "72-emoji-bytes",
        "76-emoji-bytes",
        "73-multibyte-bytes",
    ],
)
def test_register_password_length_limits(client, registration_open, password, accepted):
    response = client.post(REGISTER_URL, json={**NEW_USER, "password": password})

    assert response.status_code == (201 if accepted else 422)
    if not accepted:
        assert response.json()["detail"][0]["loc"] == ["body", "password"]


def test_register_does_not_strip_password(client, registration_open):
    client.post(REGISTER_URL, json={**NEW_USER, "password": "  senha-forte-123  "})

    assert login(client, "bruno@example.test", "  senha-forte-123  ").status_code == 200
    assert login(client, "bruno@example.test", "senha-forte-123").status_code == 401


def test_register_ignores_extra_fields(client, db_session, registration_open):
    forged_id = str(uuid.uuid4())
    payload = {
        **NEW_USER,
        "id": forged_id,
        "is_active": False,
        "password_hash": "$2b$12$forgedforgedforgedforgedforgedforgedforgedforgedforg",
        "created_at": "2000-01-01T00:00:00Z",
    }

    response = client.post(REGISTER_URL, json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["id"] != forged_id
    assert body["is_active"] is True
    assert not body["created_at"].startswith("2000")
    user = db_session.get(User, uuid.UUID(body["id"]))
    assert user.is_active is True
    assert verify_password(NEW_USER["password"], user.password_hash)


def test_register_response_never_exposes_password(client, registration_open):
    response = client.post(REGISTER_URL, json=NEW_USER)

    assert response.status_code == 201
    assert "password" not in response.json()
    assert "password_hash" not in response.json()
    assert NEW_USER["password"] not in response.text
    assert "$2b$" not in response.text


def test_register_stores_bcrypt_hash_not_the_password(client, db_session, override_settings):
    override_settings(allow_registration=True, bcrypt_rounds=DEFAULT_BCRYPT_ROUNDS)
    body = client.post(REGISTER_URL, json=NEW_USER).json()

    password_hash = db_session.get(User, uuid.UUID(body["id"])).password_hash
    assert password_hash != NEW_USER["password"]
    assert NEW_USER["password"] not in password_hash
    assert password_hash.startswith("$2b$12$")
    assert len(password_hash) == 60
    assert bcrypt.checkpw(NEW_USER["password"].encode(), password_hash.encode())


@pytest.mark.parametrize("missing", ["email", "name", "password"])
def test_register_requires_all_fields(client, registration_open, missing):
    payload = {key: value for key, value in NEW_USER.items() if key != missing}

    response = client.post(REGISTER_URL, json=payload)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", missing]


@pytest.mark.parametrize(
    ("field", "value"),
    [("email", 123), ("name", None), ("password", 12345678), ("email", ["a@b.c"])],
)
def test_register_rejects_wrong_types(client, registration_open, field, value):
    response = client.post(REGISTER_URL, json={**NEW_USER, field: value})

    assert response.status_code == 422


def test_register_rejects_form_encoded_body(client, registration_open):
    response = client.post(REGISTER_URL, data=NEW_USER)

    assert response.status_code == 422


def test_register_disabled_does_not_reveal_existing_email(client, create_user, override_settings):
    override_settings(allow_registration=False)
    create_user(email="bruno@example.test")

    response = client.post(REGISTER_URL, json=NEW_USER)

    assert response.status_code == 403


@pytest.mark.parametrize(
    ("field", "value"),
    [("email", "a\x00b@example.test"), ("name", "Ana\x00Souza")],
    ids=["email", "name"],
)
def test_register_rejects_nul_character_with_422(client, registration_open, field, value):
    response = client.post(REGISTER_URL, json={**NEW_USER, field: value})

    assert response.status_code == 422


def test_register_accepts_nul_character_in_password(client, registration_open):
    response = client.post(REGISTER_URL, json={**NEW_USER, "password": "senha\x00forte-123"})

    assert response.status_code == 201
    assert login(client, "bruno@example.test", "senha\x00forte-123").status_code == 200
    assert login(client, "bruno@example.test", "senha").status_code == 401


# --- validation error responses ---


def _post_raw(client, body: str):
    """Send a raw JSON body: needed for escapes such as \\ud800 that json.dumps cannot encode as UTF-8."""
    return client.post(REGISTER_URL, content=body.encode(), headers={"Content-Type": "application/json"})


@pytest.mark.parametrize(
    ("field", "raw_value"),
    [("email", r"a\ud800@example.test"), ("name", r"R\ud800"), ("password", r"senha-forte-\ud800")],
)
def test_register_rejects_lone_surrogate_with_422(client, registration_open, field, raw_value):
    fields = {"email": "bruno@example.test", "name": "Bruno", "password": "senha-forte-123", field: raw_value}
    body = "{" + ", ".join(f'"{key}": "{value}"' for key, value in fields.items()) + "}"

    response = _post_raw(client, body)

    assert response.status_code == 422
    error = response.json()["detail"][0]
    assert error["loc"] == ["body", field]
    assert error["msg"] == "O texto contém caracteres inválidos."


def test_validation_error_does_not_echo_the_password(client, registration_open):
    response = client.post(REGISTER_URL, json={**NEW_USER, "password": "curta-7"})

    assert response.status_code == 422
    assert "curta-7" not in response.text
    assert response.json() == {
        "detail": [
            {
                "type": "value_error",
                "loc": ["body", "password"],
                "msg": "A senha deve ter pelo menos 8 caracteres.",
            }
        ]
    }


def test_validation_errors_only_expose_type_loc_and_msg(client, registration_open):
    response = client.post(REGISTER_URL, json={"email": "invalido", "name": " ", "password": 1})

    assert response.status_code == 422
    errors = response.json()["detail"]
    assert len(errors) == 3
    assert all(set(error) == {"type", "loc", "msg"} for error in errors)
    assert not any(error["msg"].startswith("Value error") for error in errors)


def test_invalid_json_body_returns_422_without_echo(client, registration_open):
    response = _post_raw(client, '{"email": "bruno@example.test", "password": "segredo-123"')

    assert response.status_code == 422
    assert "segredo-123" not in response.text
