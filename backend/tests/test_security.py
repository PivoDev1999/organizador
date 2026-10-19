import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.security import (
    DEFAULT_BCRYPT_ROUNDS,
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    dummy_password_hash,
    hash_password,
    hash_rounds,
    verify_password,
)
from tests.helpers import b64url

SECRET = "s" * 32
FAST_ROUNDS = 4


def test_hash_and_verify_password():
    password_hash = hash_password("minha-senha-123", FAST_ROUNDS)

    assert password_hash != "minha-senha-123"
    assert verify_password("minha-senha-123", password_hash)
    assert not verify_password("outra-senha", password_hash)


def test_hash_password_rejects_more_than_72_bytes():
    with pytest.raises(ValueError, match="72 bytes"):
        hash_password("ç" * 37, FAST_ROUNDS)


def test_verify_password_returns_false_for_more_than_72_bytes():
    assert not verify_password("a" * 73, hash_password("a" * 72, FAST_ROUNDS))


def test_dummy_hash_is_a_valid_bcrypt_hash():
    assert not verify_password("anything", dummy_password_hash(FAST_ROUNDS))


def test_token_round_trip():
    user_id = uuid.uuid4()
    token = create_access_token(user_id, SECRET, expires_minutes=5)

    assert decode_access_token(token, SECRET) == user_id
    claims = jwt.decode(token, SECRET, algorithms=["HS256"])
    assert claims["exp"] - claims["iat"] == 5 * 60


def test_expired_token_is_rejected():
    past = datetime.now(UTC) - timedelta(minutes=10)
    token = create_access_token(uuid.uuid4(), SECRET, expires_minutes=5, now=past)

    with pytest.raises(InvalidTokenError):
        decode_access_token(token, SECRET)


def test_token_signed_with_other_key_is_rejected():
    token = create_access_token(uuid.uuid4(), "o" * 32, expires_minutes=5)

    with pytest.raises(InvalidTokenError):
        decode_access_token(token, SECRET)


def test_tampered_token_is_rejected():
    header, payload, signature = create_access_token(uuid.uuid4(), SECRET, expires_minutes=5).split(".")
    tampered = f"{header}.{payload}.{signature[:-2]}xx"

    with pytest.raises(InvalidTokenError):
        decode_access_token(tampered, SECRET)


@pytest.mark.parametrize(
    "claims",
    [
        {"sub": "not-a-uuid"},
        {"sub": None},
        {"exp": None},
        {"iat": None},
        {"type": None},
        {"type": "refresh"},
        {"type": "ACCESS"},
    ],
)
def test_token_with_bad_or_missing_claims_is_rejected(claims):
    now = datetime.now(UTC)
    payload = {
        "sub": str(uuid.uuid4()),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        **claims,
    }
    payload = {key: value for key, value in payload.items() if value is not None}
    token = jwt.encode(payload, SECRET, algorithm="HS256")

    with pytest.raises(InvalidTokenError):
        decode_access_token(token, SECRET)


def test_garbage_token_is_rejected():
    with pytest.raises(InvalidTokenError):
        decode_access_token("not.a.jwt", SECRET)


# --- algorithm and signature ---


def _valid_claims(user_id: uuid.UUID | None = None) -> dict:
    now = datetime.now(UTC)
    return {
        "sub": str(user_id or uuid.uuid4()),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
    }


@pytest.mark.parametrize("signature", ["", "c2lnbmF0dXJl"], ids=["empty-signature", "fake-signature"])
def test_unsigned_alg_none_token_is_rejected(signature):
    token = f"{b64url({'alg': 'none', 'typ': 'JWT'})}.{b64url(_valid_claims())}.{signature}"

    with pytest.raises(InvalidTokenError):
        decode_access_token(token, SECRET)


@pytest.mark.parametrize("algorithm", ["HS384", "HS512"])
def test_token_signed_with_right_key_but_other_algorithm_is_rejected(algorithm):
    long_secret = SECRET * 2  # long enough for HS512, so PyJWT does not warn
    token = jwt.encode(_valid_claims(), long_secret, algorithm=algorithm)

    with pytest.raises(InvalidTokenError):
        decode_access_token(token, long_secret)


def test_token_header_declares_hs256():
    token = create_access_token(uuid.uuid4(), SECRET, expires_minutes=5)

    assert jwt.get_unverified_header(token)["alg"] == "HS256"


@pytest.mark.parametrize(
    "claims",
    [
        {"sub": 123},
        {"sub": ""},
        {"sub": str(uuid.uuid4()).upper()[:-1]},
        {"exp": "tomorrow"},
        {"iat": "yesterday"},
    ],
    ids=["int-sub", "empty-sub", "truncated-uuid-sub", "string-exp", "string-iat"],
)
def test_token_with_malformed_claim_types_is_rejected(claims):
    token = jwt.encode({**_valid_claims(), **claims}, SECRET, algorithm="HS256")

    with pytest.raises(InvalidTokenError):
        decode_access_token(token, SECRET)


@pytest.mark.parametrize("token", ["", "a.b", "a.b.c.d", "Bearer x.y.z"])
def test_structurally_invalid_token_is_rejected(token):
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, SECRET)


# --- expiration (JWT times are whole seconds; exp is computed relative to the current second) ---


def _issued_for_exp_in(seconds: int) -> datetime:
    """`now` to pass to create_access_token(expires_minutes=5) so that exp = current second + `seconds`."""
    return datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=seconds) - timedelta(minutes=5)


@pytest.mark.parametrize(
    ("seconds_left", "valid"),
    [(300, True), (5, True), (0, False), (-1, False)],
    ids=["at-issue", "seconds-before-exp", "exp-reached", "one-second-after-exp"],
)
def test_token_expires_at_exp(seconds_left, valid):
    user_id = uuid.uuid4()
    token = create_access_token(user_id, SECRET, expires_minutes=5, now=_issued_for_exp_in(seconds_left))

    if valid:
        assert decode_access_token(token, SECRET) == user_id
    else:
        with pytest.raises(InvalidTokenError):
            decode_access_token(token, SECRET)


def test_token_issued_in_the_future_is_rejected():
    token = create_access_token(
        uuid.uuid4(), SECRET, expires_minutes=5, now=datetime.now(UTC) + timedelta(minutes=1)
    )

    with pytest.raises(InvalidTokenError):
        decode_access_token(token, SECRET)


def test_create_access_token_uses_current_time_by_default():
    before = int(datetime.now(UTC).timestamp())
    token = create_access_token(uuid.uuid4(), SECRET, expires_minutes=60)
    after = int(datetime.now(UTC).timestamp())

    claims = jwt.decode(token, SECRET, algorithms=["HS256"])
    assert before <= claims["iat"] <= after
    assert claims["exp"] == claims["iat"] + 3600


def test_token_contains_only_expected_claims():
    user_id = uuid.uuid4()
    token = create_access_token(user_id, SECRET, expires_minutes=5)

    claims = jwt.decode(token, SECRET, algorithms=["HS256"])
    assert set(claims) == {"sub", "type", "iat", "exp"}
    assert claims["type"] == "access"
    assert claims["sub"] == str(user_id)


# --- passwords ---


def test_hash_password_produces_bcrypt_hash_with_cost_12_and_random_salt():
    first = hash_password("minha-senha-123", DEFAULT_BCRYPT_ROUNDS)
    second = hash_password("minha-senha-123", DEFAULT_BCRYPT_ROUNDS)

    assert first.startswith("$2b$12$")
    assert len(first) == 60
    assert first != second
    assert verify_password("minha-senha-123", second)


@pytest.mark.parametrize(
    "attempt",
    ["MINHA-SENHA-123", "Minha-senha-123", "minha-senha-123 ", " minha-senha-123", "minha-senha-12"],
)
def test_verify_password_is_exact(attempt):
    assert not verify_password(attempt, hash_password("minha-senha-123", FAST_ROUNDS))


def test_hash_password_accepts_exactly_72_bytes_multibyte():
    password = "😀" * 18  # 4 bytes each

    assert verify_password(password, hash_password(password, FAST_ROUNDS))


def test_hash_password_rejects_73_bytes_multibyte():
    with pytest.raises(ValueError, match="72 bytes"):
        hash_password("a" + "á" * 36, FAST_ROUNDS)


def test_password_with_nul_byte_is_not_truncated():
    password_hash = hash_password("abcdefgh\x00xyz", FAST_ROUNDS)

    assert verify_password("abcdefgh\x00xyz", password_hash)
    assert not verify_password("abcdefgh", password_hash)


@pytest.mark.parametrize("rounds", [FAST_ROUNDS, DEFAULT_BCRYPT_ROUNDS])
def test_dummy_hash_has_the_same_cost_as_real_hashes(rounds):
    assert hash_rounds(dummy_password_hash(rounds)) == rounds
    assert hash_rounds(hash_password("minha-senha-123", rounds)) == rounds


def test_dummy_hash_is_computed_once_per_cost():
    assert dummy_password_hash(FAST_ROUNDS) is dummy_password_hash(FAST_ROUNDS)
    assert dummy_password_hash(FAST_ROUNDS) != dummy_password_hash(FAST_ROUNDS + 1)
