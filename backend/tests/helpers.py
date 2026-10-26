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


# --- files -----------------------------------------------------------------------------------------

FILES_URL = "/api/files"
# Minimal valid headers of each inline-safe format (the signature is what matters).
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 24
GIF = b"GIF89a" + b"\x00" * 24
WEBP = b"RIFF\x10\x00\x00\x00WEBPVP8 " + b"\x00" * 16
PDF = b"%PDF-1.7\n" + b"\x00" * 24
HTML = b"<!doctype html><script>alert(document.cookie)</script>"
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>'


SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "content-security-policy": "default-src 'none'; sandbox",
    "cache-control": "private, no-store",
}


def assert_security_headers(response: Response) -> None:
    """Every response under /api/files, errors included, carries these headers."""
    assert {name: response.headers.get(name) for name in SECURITY_HEADERS} == SECURITY_HEADERS


def upload(
    client: TestClient,
    headers: dict[str, str],
    entity_type: str,
    entity_id: uuid.UUID | str,
    content: bytes = PNG,
    name: str = "foto.png",
    content_type: str | None = "image/png",
) -> Response:
    file = (name, content, content_type) if content_type else (name, content)
    return client.post(
        FILES_URL,
        data={"entity_type": entity_type, "entity_id": str(entity_id)},
        files={"file": file},
        headers=headers,
    )
