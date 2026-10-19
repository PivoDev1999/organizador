import secrets
import uuid
from datetime import UTC, datetime, timedelta
from functools import cache

import bcrypt
import jwt

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TYPE = "access"
BCRYPT_MAX_BYTES = 72
DEFAULT_BCRYPT_ROUNDS = 12
MIN_BCRYPT_ROUNDS = 4
MAX_BCRYPT_ROUNDS = 31


class InvalidTokenError(Exception):
    pass


def hash_password(password: str, rounds: int = DEFAULT_BCRYPT_ROUNDS) -> str:
    encoded = password.encode()
    if len(encoded) > BCRYPT_MAX_BYTES:
        raise ValueError(f"password longer than {BCRYPT_MAX_BYTES} bytes")
    return bcrypt.hashpw(encoded, bcrypt.gensalt(rounds)).decode()


@cache
def dummy_password_hash(rounds: int = DEFAULT_BCRYPT_ROUNDS) -> str:
    """Hash checked when the e-mail does not exist, so the response takes as long as a real check.

    It must use the same cost as real hashes, otherwise timing reveals whether the e-mail exists.
    Computed once per cost and cached.
    """
    return hash_password(secrets.token_urlsafe(32), rounds)


def hash_rounds(password_hash: str) -> int:
    """Cost factor of a bcrypt hash ("$2b$12$..." -> 12)."""
    return int(password_hash.split("$")[2])


def verify_password(password: str, password_hash: str) -> bool:
    """Raise ValueError when `password_hash` is not a valid bcrypt hash (corrupted data)."""
    try:
        encoded = password.encode()
    except UnicodeEncodeError:
        return False
    if len(encoded) > BCRYPT_MAX_BYTES:
        return False
    return bcrypt.checkpw(encoded, password_hash.encode())


def create_access_token(
    user_id: uuid.UUID, secret_key: str, expires_minutes: int, now: datetime | None = None
) -> str:
    issued_at = now or datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "type": ACCESS_TOKEN_TYPE,
        "iat": issued_at,
        "exp": issued_at + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, secret_key: str) -> uuid.UUID:
    """Return the user id from a valid token; raise InvalidTokenError otherwise."""
    try:
        payload = jwt.decode(
            token, secret_key, algorithms=[JWT_ALGORITHM], options={"require": ["sub", "type", "exp", "iat"]}
        )
        if payload["type"] != ACCESS_TOKEN_TYPE:
            raise InvalidTokenError("not an access token")
        return uuid.UUID(payload["sub"])
    except (jwt.InvalidTokenError, ValueError, TypeError) as exc:
        raise InvalidTokenError(str(exc)) from exc
