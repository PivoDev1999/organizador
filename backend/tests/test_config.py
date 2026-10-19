import pytest
from pydantic import ValidationError

from app.core.config import Settings

STRONG_KEY = "x" * 32


def build_settings(**overrides) -> Settings:
    values = {
        "environment": "development",
        "secret_key": STRONG_KEY,
        "postgres_user": "organizador",
        "postgres_password": "db-password",
        "postgres_db": "organizador",
        "s3_endpoint_url": "http://localhost:3900",
        "s3_access_key_id": "GK0000",
        "s3_secret_access_key": "s3-secret",
        "s3_bucket": "organizador",
        **overrides,
    }
    return Settings(_env_file=None, **values)


@pytest.mark.parametrize("field", ["secret_key", "postgres_password", "s3_secret_access_key"])
@pytest.mark.parametrize("environment", ["development", "production"])
def test_rejects_change_me_placeholder(field, environment):
    with pytest.raises(ValidationError, match=field.upper()):
        build_settings(environment=environment, **{field: "change-me"})


@pytest.mark.parametrize("secret_key", ["short", "x" * 31, " " + "x" * 30 + " "])
@pytest.mark.parametrize("environment", ["development", "production"])
def test_short_secret_key_is_rejected_in_every_environment(environment, secret_key):
    with pytest.raises(ValidationError, match="at least 32 characters"):
        build_settings(environment=environment, secret_key=secret_key)


def test_valid_production_settings():
    assert build_settings(environment="production").environment == "production"


def test_auth_defaults():
    settings = build_settings()

    assert settings.allow_registration is False
    assert settings.access_token_expire_minutes == 10080
    assert settings.app_timezone == "America/Sao_Paulo"


def test_timezone_property_returns_zoneinfo():
    assert build_settings(app_timezone="UTC").timezone.key == "UTC"


@pytest.mark.parametrize("value", ["Mars/Olympus_Mons", "", "../etc/passwd"])
def test_rejects_invalid_timezone(value):
    with pytest.raises(ValidationError, match="APP_TIMEZONE"):
        build_settings(app_timezone=value)


@pytest.mark.parametrize("minutes", [0, -1])
def test_rejects_non_positive_token_expiration(minutes):
    with pytest.raises(ValidationError, match="access_token_expire_minutes"):
        build_settings(access_token_expire_minutes=minutes)


def test_rejects_empty_secret_key_even_in_development():
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        build_settings(environment="development", secret_key="")


@pytest.mark.parametrize("environment", ["development", "production"])
def test_secret_key_of_exactly_32_characters_is_accepted(environment):
    assert build_settings(environment=environment, secret_key="x" * 32).secret_key == "x" * 32


def test_token_expiration_is_read_from_environment(monkeypatch):
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15")

    assert build_settings().access_token_expire_minutes == 15


@pytest.mark.parametrize("secret_key", [" ", "\t\n  "])
@pytest.mark.parametrize("environment", ["development", "production"])
def test_rejects_blank_secret_key(environment, secret_key):
    with pytest.raises(ValidationError, match="SECRET_KEY must not be empty"):
        build_settings(environment=environment, secret_key=secret_key)


def test_bcrypt_rounds_defaults_to_12(monkeypatch):
    monkeypatch.delenv("BCRYPT_ROUNDS", raising=False)

    assert build_settings().bcrypt_rounds == 12


@pytest.mark.parametrize("rounds", [4, 31])
def test_bcrypt_rounds_accepts_bcrypt_range(rounds):
    assert build_settings(bcrypt_rounds=rounds).bcrypt_rounds == rounds


@pytest.mark.parametrize("rounds", [3, 32])
def test_bcrypt_rounds_rejects_values_outside_bcrypt_range(rounds):
    with pytest.raises(ValidationError, match="bcrypt_rounds"):
        build_settings(bcrypt_rounds=rounds)
