from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

# The single .env lives at the repository root, shared with docker compose.
ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


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
