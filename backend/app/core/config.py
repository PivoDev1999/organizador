import os
from functools import lru_cache
from pathlib import Path
from typing import Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

from app.core.security import DEFAULT_BCRYPT_ROUNDS, MAX_BCRYPT_ROUNDS, MIN_BCRYPT_ROUNDS

REPO_ROOT = Path(__file__).resolve().parents[3]
# By default the single .env at the repository root, shared with docker compose.
ENV_FILE = Path(os.environ.get("ENV_FILE") or REPO_ROOT / ".env")

PLACEHOLDER = "change-me"
SECRET_FIELDS = ("secret_key", "postgres_password", "s3_secret_access_key")
MIN_SECRET_KEY_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    app_name: str = "Organizador"
    environment: str = "development"
    secret_key: str
    access_token_expire_minutes: int = Field(default=10080, gt=0)
    allow_registration: bool = False
    app_timezone: str = "America/Sao_Paulo"
    # Internal knob: tests lower it to keep the suite fast. Keep the default in real deployments.
    bcrypt_rounds: int = Field(default=DEFAULT_BCRYPT_ROUNDS, ge=MIN_BCRYPT_ROUNDS, le=MAX_BCRYPT_ROUNDS)
    # Internal knob: the dashboard refuses to answer (500) without its consistent snapshot. Only the test
    # suite turns it off, because its session runs inside savepoints, where the snapshot cannot be set.
    dashboard_require_snapshot: bool = True

    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_test_db: str = "organizador_test"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    s3_endpoint_url: str
    s3_region: str = "garage"
    s3_access_key_id: str
    s3_secret_access_key: str
    s3_bucket: str
    # Bucket of the storage integration tests (created by garage-init with the same key).
    s3_test_bucket: str = "organizador-test"
    # Upload limit per file, in MiB (1 MB here = 1024 * 1024 bytes).
    max_upload_mb: int = Field(default=20, ge=1, le=1024)

    seed_user_password: str | None = None

    # Swagger UI assets (npm package swagger-ui-dist, a frontend devDependency), served by the API under
    # /api/docs-assets in development. In the Docker stack Nginx serves them and this folder does not exist.
    swagger_ui_dir: Path = REPO_ROOT / "frontend" / "node_modules" / "swagger-ui-dist"

    @field_validator("app_timezone")
    @classmethod
    def _check_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"APP_TIMEZONE {value!r} is not a valid IANA time zone") from None
        return value

    @model_validator(mode="after")
    def _check_secrets(self) -> Self:
        placeholders = [name.upper() for name in SECRET_FIELDS if getattr(self, name) == PLACEHOLDER]
        if placeholders:
            raise ValueError(f"replace the '{PLACEHOLDER}' placeholder in .env: {', '.join(placeholders)}")
        if not self.secret_key.strip():
            raise ValueError("SECRET_KEY must not be empty")
        # Required in every environment: the home server itself runs with ENVIRONMENT=development.
        if len(self.secret_key.strip()) < MIN_SECRET_KEY_LENGTH:
            raise ValueError(f"SECRET_KEY must have at least {MIN_SECRET_KEY_LENGTH} characters")
        return self

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.app_timezone)

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def database_url(self) -> URL:
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
