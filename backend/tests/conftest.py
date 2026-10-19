import os

import pytest

# Point the whole app at the test database before anything creates an engine.
from app.core.config import get_settings  # noqa: E402

_main_db = get_settings().postgres_db
_test_db = get_settings().postgres_test_db
# Tests drop the whole schema (downgrade base), so never let them touch the real database.
if _test_db == _main_db or not _test_db.endswith("_test"):
    pytest.exit(
        f"Refusing to run: POSTGRES_TEST_DB={_test_db!r} must end with '_test' and differ from "
        f"POSTGRES_DB={_main_db!r}.",
        returncode=1,
    )

os.environ["POSTGRES_DB"] = _test_db
get_settings.cache_clear()

from collections.abc import Iterator  # noqa: E402
from pathlib import Path  # noqa: E402

from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from alembic import command  # noqa: E402
from app.core.database import engine  # noqa: E402
from app.main import app  # noqa: E402

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


@pytest.fixture(scope="session")
def alembic_config() -> Config:
    return Config(str(ALEMBIC_INI))


@pytest.fixture(scope="session", autouse=True)
def migrated_database(alembic_config: Config) -> Iterator[None]:
    command.upgrade(alembic_config, "head")
    yield


@pytest.fixture
def db_session() -> Iterator[Session]:
    """Session bound to an outer transaction that is rolled back after the test.

    Commits and rollbacks inside the test only touch savepoints, so nothing leaks between tests.
    """
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
