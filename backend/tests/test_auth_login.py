from datetime import UTC, datetime

import jwt
import pytest

from app.core.config import get_settings
from app.core.security import dummy_password_hash
from app.services import auth as auth_service
from tests.helpers import (
    LOGIN_URL,
    ME_URL,
    REGISTER_URL,
    TEST_PASSWORD,
    auth_header,
    login,
)

NEW_USER = {"email": "  Bruno@Example.TEST ", "name": "  Bruno   Silva ", "password": "senha-forte-123"}


def test_login_returns_bearermake_token(client, create_user):
    create_user(email="ana@example.test")

    response = login(client, "  ANA@example.test", TEST_PASSWORD)

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


@pytest.mark.parametrize(
    ("email", "password", "user_fields"),
    [
        ("ana@example.test", "senha-errada", {}),
        ("ninguem@example.test", TEST_PASSWORD, {}),
        ("ana@example.test", TEST_PASSWORD, {"is_active": False}),
    ],
    ids=["wrong-password", "unknown-email", "inactive-user"],
)
def test_login_failures_return_generic_401(client, create_user, email, password, user_fields):
    create_user(email="ana@example.test", **user_fields)

    response = login(client, email, password)

    assert response.status_code == 401
    assert response.json()["detail"] == "E-mail ou senha inválidos."
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_login_with_unknown_email_still_checks_a_password(client, monkeypatch):
    calls = []
    original = auth_service.verify_password
    monkeypatch.setattr(auth_service, "verify_password", lambda *args: calls.append(args) or original(*args))

    response = login(client, "ninguem@example.test", "qualquer-senha")

    assert response.status_code == 401
    assert calls == [("qualquer-senha", dummy_password_hash(get_settings().bcrypt_rounds))]


def test_full_flow_register_login_me(client, registration_open):
    client.post(REGISTER_URL, json=NEW_USER)
    token = login(client, "bruno@example.test", NEW_USER["password"]).json()["access_token"]

    response = client.get(ME_URL, headers=auth_header(token))

    assert response.status_code == 200
    assert response.json()["email"] == "bruno@example.test"


@pytest.mark.parametrize(
    "email",
    ["ANA@EXAMPLE.TEST", "  Ana@Example.Test  ", "\tana@example.test\n"],
    ids=["upper", "mixed-with-spaces", "tab-newline"],
)
def test_login_normalizes_email(client, create_user, email):
    create_user(email="ana@example.test")

    assert login(client, email, TEST_PASSWORD).status_code == 200


def test_login_finds_user_stored_with_uppercase_email(client, create_user):
    create_user(email="Ana@Example.TEST")

    assert login(client, "ana@example.test", TEST_PASSWORD).status_code == 200


@pytest.mark.parametrize(
    "password",
    [TEST_PASSWORD.upper(), TEST_PASSWORD.swapcase(), f" {TEST_PASSWORD}", f"{TEST_PASSWORD} "],
    ids=["upper", "swapcase", "leading-space", "trailing-space"],
)
def test_login_rejects_password_variations(client, create_user, password):
    create_user(email="ana@example.test")

    response = client.post(LOGIN_URL, data={"username": "ana@example.test", "password": password})

    assert response.status_code == 401
    assert response.json()["detail"] == "E-mail ou senha inválidos."


def test_login_with_password_over_72_bytes_returns_401(client, create_user):
    create_user(email="ana@example.test")

    response = login(client, "ana@example.test", "á" * 50)

    assert response.status_code == 401


def test_login_rejects_email_with_internal_space(client, create_user):
    create_user(email="ana@example.test")

    assert login(client, "ana @example.test", TEST_PASSWORD).status_code == 401


@pytest.mark.parametrize(
    "data",
    [{"password": TEST_PASSWORD}, {"username": "ana@example.test"}, {}],
    ids=["no-username", "no-password", "empty"],
)
def test_login_requires_form_fields(client, create_user, data):
    create_user(email="ana@example.test")

    response = client.post(LOGIN_URL, data=data)

    assert response.status_code == 422


def test_login_with_json_body_returns_422(client, create_user):
    create_user(email="ana@example.test")

    response = client.post(LOGIN_URL, json={"username": "ana@example.test", "password": TEST_PASSWORD})

    assert response.status_code == 422


def test_login_rejects_unsupported_grant_type(client, create_user):
    create_user(email="ana@example.test")

    response = client.post(
        LOGIN_URL,
        data={"username": "ana@example.test", "password": TEST_PASSWORD, "grant_type": "client_credentials"},
    )

    assert response.status_code == 422


def test_login_accepts_password_grant_type(client, create_user):
    create_user(email="ana@example.test")

    response = client.post(
        LOGIN_URL, data={"username": "ana@example.test", "password": TEST_PASSWORD, "grant_type": "password"}
    )

    assert response.status_code == 200


def test_login_failure_responses_are_identical(client, create_user):
    create_user(email="ana@example.test")
    create_user(email="inativa@example.test", is_active=False)

    responses = [
        login(client, "ninguem@example.test", TEST_PASSWORD),
        login(client, "ana@example.test", "senha-errada"),
        login(client, "inativa@example.test", TEST_PASSWORD),
    ]

    assert {r.status_code for r in responses} == {401}
    assert len({r.text for r in responses}) == 1
    assert len({r.headers["WWW-Authenticate"] for r in responses}) == 1


def test_login_inactive_user_with_wrong_password_returns_same_401(client, create_user):
    create_user(email="ana@example.test", is_active=False)

    response = login(client, "ana@example.test", "senha-errada")

    assert response.status_code == 401
    assert response.json()["detail"] == "E-mail ou senha inválidos."


def test_login_with_existing_email_checks_password_against_user_hash(client, create_user, monkeypatch):
    user = create_user(email="ana@example.test")
    calls = []
    original = auth_service.verify_password
    monkeypatch.setattr(auth_service, "verify_password", lambda *args: calls.append(args) or original(*args))

    login(client, "ana@example.test", "senha-errada")

    assert calls == [("senha-errada", user.password_hash)]


def test_login_with_nul_character_in_email_returns_401(client, create_user):
    create_user(email="ana@example.test")

    response = login(client, "ana\x00@example.test", TEST_PASSWORD)

    assert response.status_code == 401


def test_login_tokens_identify_the_right_user(client, create_user):
    ana = create_user(email="ana@example.test")
    bruno = create_user(email="bruno@example.test", name="Bruno")

    ana_token = login(client, "ana@example.test", TEST_PASSWORD).json()["access_token"]
    bruno_token = login(client, "bruno@example.test", TEST_PASSWORD).json()["access_token"]

    assert client.get(ME_URL, headers=auth_header(ana_token)).json()["id"] == str(ana.id)
    assert client.get(ME_URL, headers=auth_header(bruno_token)).json()["id"] == str(bruno.id)


@pytest.mark.parametrize("minutes", [1, 30, 10080])
def test_login_token_uses_access_token_expire_minutes(client, create_user, override_settings, minutes):
    override_settings(access_token_expire_minutes=minutes)
    create_user(email="ana@example.test")

    token = login(client, "ana@example.test", TEST_PASSWORD).json()["access_token"]

    claims = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
    assert claims["exp"] - claims["iat"] == minutes * 60
    assert abs(claims["iat"] - datetime.now(UTC).timestamp()) < 60


def test_login_token_is_signed_with_configured_secret_key(client, create_user, override_settings):
    settings = override_settings(secret_key="k" * 40)
    user = create_user(email="ana@example.test")

    token = login(client, "ana@example.test", TEST_PASSWORD).json()["access_token"]

    claims = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    assert claims["sub"] == str(user.id)
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(token, "x" * 40, algorithms=["HS256"])
    assert client.get(ME_URL, headers=auth_header(token)).status_code == 200


def test_login_with_corrupted_stored_hash_returns_generic_401(client, db_session, create_user):
    user = create_user(email="ana@example.test")
    user.password_hash = "not-a-bcrypt-hash"
    db_session.commit()

    response = login(client, "ana@example.test", TEST_PASSWORD)

    assert response.status_code == 401
    assert response.json()["detail"] == "E-mail ou senha inválidos."


def test_login_rehashes_password_when_cost_changes(client, db_session, create_user, override_settings):
    user = create_user(email="ana@example.test")
    override_settings(bcrypt_rounds=5)

    assert login(client, "ana@example.test", TEST_PASSWORD).status_code == 200

    db_session.refresh(user)
    assert user.password_hash.startswith("$2b$05$")
    assert login(client, "ana@example.test", TEST_PASSWORD).status_code == 200


def test_login_does_not_downgrade_hash_cost(client, db_session, create_user, override_settings):
    user = create_user(email="ana@example.test", rounds=5)
    override_settings(bcrypt_rounds=4)

    assert login(client, "ana@example.test", TEST_PASSWORD).status_code == 200

    db_session.refresh(user)
    assert user.password_hash.startswith("$2b$05$")
