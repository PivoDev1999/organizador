import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import get_settings
from tests.helpers import (
    ME_URL,
    TEST_PASSWORD,
    auth_header,
    b64url,
    login,
    make_token,
)


def _claims(user_id: uuid.UUID, **changes) -> dict:
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        **changes,
    }
    return {key: value for key, value in claims.items() if value is not None}


def _alg_none_token(user_id: uuid.UUID) -> str:
    return f"{b64url({'alg': 'none', 'typ': 'JWT'})}.{b64url(_claims(user_id))}."


def _hs512_token(user_id: uuid.UUID) -> str:
    return jwt.encode(_claims(user_id), get_settings().secret_key * 4, algorithm="HS512")


def _signed(claims: dict) -> str:
    return jwt.encode(claims, get_settings().secret_key, algorithm="HS256")


def test_me_returns_authenticated_user(client, create_user):
    user = create_user(email="ana@example.test", name="Ana Souza")
    token = login(client, "ana@example.test", TEST_PASSWORD).json()["access_token"]

    response = client.get(ME_URL, headers=auth_header(token))

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(user.id)
    assert body["email"] == "ana@example.test"
    assert body["name"] == "Ana Souza"
    assert "password_hash" not in body


@pytest.mark.parametrize(
    "make_headers",
    [
        lambda user: {},
        lambda user: auth_header("not-a-jwt"),
        lambda user: auth_header(make_token(user.id, secret="x" * 32)),
        lambda user: auth_header(make_token(user.id, now=datetime.now(UTC) - timedelta(hours=1))),
        lambda user: auth_header(make_token(uuid.uuid4())),
        lambda user: {"Authorization": f"Basic {make_token(user.id)}"},
    ],
    ids=["missing", "garbage", "wrong-key", "expired", "unknown-user", "wrong-scheme"],
)
def test_me_rejects_invalid_authentication(client, create_user, make_headers):
    user = create_user()

    response = client.get(ME_URL, headers=make_headers(user))

    assert response.status_code == 401
    assert response.json()["detail"] == "Não autenticado."
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_me_rejects_inactive_user(client, create_user):
    user = create_user(is_active=False)

    response = client.get(ME_URL, headers=auth_header(make_token(user.id)))

    assert response.status_code == 401
    assert response.json()["detail"] == "Não autenticado."


@pytest.mark.parametrize(
    "make_headers",
    [
        lambda user: {"Authorization": "Bearer"},
        lambda user: {"Authorization": "Bearer "},
        lambda user: {"Authorization": ""},
        lambda user: {"Authorization": "Basic xyz"},
        lambda user: {"Authorization": make_token(user.id)},
        lambda user: {"Authorization": f"Token {make_token(user.id)}"},
        lambda user: {"Authorization": f"Bearer {make_token(user.id)} extra"},
        lambda user: auth_header(_alg_none_token(user.id)),
        lambda user: auth_header(_hs512_token(user.id)),
        lambda user: auth_header(_signed(_claims(user.id, sub=None))),
        lambda user: auth_header(_signed(_claims(user.id, type=None))),
        lambda user: auth_header(_signed(_claims(user.id, type="refresh"))),
        lambda user: auth_header(make_token(user.id, now=datetime.now(UTC) + timedelta(hours=1))),
    ],
    ids=[
        "bearer-without-token",
        "bearer-with-empty-token",
        "empty-header",
        "basic-scheme",
        "token-without-scheme",
        "token-scheme",
        "trailing-garbage",
        "alg-none",
        "hs512",
        "null-sub",
        "missing-type",
        "refresh-type",
        "issued-in-future",
    ],
)
def test_me_rejects_malformed_authentication(client, create_user, make_headers):
    user = create_user()

    response = client.get(ME_URL, headers=make_headers(user))

    assert response.status_code == 401
    assert response.json()["detail"] == "Não autenticado."
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("scheme", ["bearer", "BEARER", "BeArEr"])
def test_me_accepts_bearer_scheme_case_insensitively(client, create_user, scheme):
    user = create_user()

    response = client.get(ME_URL, headers={"Authorization": f"{scheme} {make_token(user.id)}"})

    assert response.status_code == 200


def test_me_does_not_accept_token_in_query_string(client, create_user):
    user = create_user()

    response = client.get(ME_URL, params={"access_token": make_token(user.id)})

    assert response.status_code == 401


def test_me_rejects_token_of_deleted_user(client, db_session, create_user):
    user = create_user()
    token = make_token(user.id)
    assert client.get(ME_URL, headers=auth_header(token)).status_code == 200

    db_session.delete(user)
    db_session.commit()

    response = client.get(ME_URL, headers=auth_header(token))
    assert response.status_code == 401
    assert response.json()["detail"] == "Não autenticado."


def test_me_rejects_user_deactivated_after_token_was_issued(client, db_session, create_user):
    user = create_user(email="ana@example.test")
    token = login(client, "ana@example.test", TEST_PASSWORD).json()["access_token"]
    assert client.get(ME_URL, headers=auth_header(token)).status_code == 200

    user.is_active = False
    db_session.commit()

    assert client.get(ME_URL, headers=auth_header(token)).status_code == 401


def test_me_rejects_token_after_secret_key_rotation(client, create_user, override_settings):
    user = create_user()
    token = make_token(user.id)
    override_settings(secret_key="r" * 32)

    assert client.get(ME_URL, headers=auth_header(token)).status_code == 401


def test_me_response_has_only_public_fields(client, create_user):
    user = create_user()

    response = client.get(ME_URL, headers=auth_header(make_token(user.id)))

    assert set(response.json()) == {"id", "email", "name", "is_active", "created_at"}
    assert "$2b$" not in response.text
    assert TEST_PASSWORD not in response.text


@pytest.mark.parametrize(
    ("seconds_left", "status_code"), [(5, 200), (0, 401)], ids=["seconds-before-exp", "exp-reached"]
)
def test_me_token_expiration_boundary(client, create_user, seconds_left, status_code):
    user = create_user()
    # JWT times are whole seconds: with 0 seconds left, exp <= now already when the request arrives.
    exp = datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=seconds_left)
    token = make_token(user.id, minutes=5, now=exp - timedelta(minutes=5))

    assert client.get(ME_URL, headers=auth_header(token)).status_code == status_code


@pytest.mark.parametrize("method", ["post", "put", "delete"])
def test_me_only_allows_get(client, create_user, method):
    user = create_user()

    response = client.request(method.upper(), ME_URL, headers=auth_header(make_token(user.id)))

    assert response.status_code == 405
