import pytest
from pydantic import ValidationError

from app.core.config import Settings

STRONG_KEY = "x" * 32


def make_settings(**overrides) -> Settings:
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
        make_settings(environment=environment, **{field: "change-me"})


def test_short_secret_key_is_allowed_in_development():
    assert make_settings(secret_key="short").secret_key == "short"


def test_short_secret_key_is_rejected_outside_development():
    with pytest.raises(ValidationError, match="at least 32 characters"):
        make_settings(environment="production", secret_key="x" * 31)


def test_valid_production_settings():
    assert make_settings(environment="production").environment == "production"
