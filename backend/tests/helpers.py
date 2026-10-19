"""Shared test helpers (fixtures live in conftest.py)."""

import base64
import json
import uuid
from datetime import datetime

from fastapi.testclient import TestClient
from httpx import Response

from app.core.config import Settings, get_settings
from app.core.security import create_access_token

REGISTER_URL = "/api/auth/register"
LOGIN_URL = "/api/auth/login"
ME_URL = "/api/auth/me"

TEST_PASSWORD = "correct-horse-battery"


def make_settings(**changes) -> Settings:
    """Current settings with `changes` applied and validated (an invalid override fails the test)."""
    return Settings.model_validate({**get_settings().model_dump(), **changes})


def b64url(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


def login(client: TestClient, email: str, password: str) -> Response:
    return client.post(LOGIN_URL, data={"username": email, "password": password})


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def make_token(
    user_id: uuid.UUID, secret: str | None = None, minutes: int = 5, now: datetime | None = None
) -> str:
    return create_access_token(user_id, secret or get_settings().secret_key, minutes, now=now)
