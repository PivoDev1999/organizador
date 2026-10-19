import os
from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

# By default the single .env at the repository root, shared with docker compose.
ENV_FILE = Path(os.environ.get("ENV_FILE") or Path(__file__).resolve().parents[3] / ".env")

PLACEHOLDER = "change-me"
SECRET_FIELDS = ("secret_key", "postgres_password", "s3_secret_access_key")
MIN_SECRET_KEY_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    app_name: str = "Organizador"
    environment: str = "development"
    secret_key: str

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

    seed_user_password: str | None = None

    @model_validator(mode="after")
    def _check_secrets(self) -> Self:
        placeholders = [name.upper() for name in SECRET_FIELDS if getattr(self, name) == PLACEHOLDER]
        if placeholders:
            raise ValueError(f"replace the '{PLACEHOLDER}' placeholder in .env: {', '.join(placeholders)}")
        if self.environment != "development" and len(self.secret_key) < MIN_SECRET_KEY_LENGTH:
            raise ValueError(
                f"SECRET_KEY must have at least {MIN_SECRET_KEY_LENGTH} characters outside development"
            )
        return self

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
