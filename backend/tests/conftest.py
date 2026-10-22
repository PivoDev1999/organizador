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
# Minimum bcrypt cost keeps the suite fast; tests that check the production cost pass it explicitly.
os.environ["BCRYPT_ROUNDS"] = "4"
get_settings.cache_clear()

from collections.abc import Callable, Iterator  # noqa: E402
from datetime import UTC, datetime  # noqa: E402
from pathlib import Path  # noqa: E402

from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from alembic import command  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.core.database import SESSION_OPTIONS, engine, get_db  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Task, User  # noqa: E402
from tests.helpers import TEST_PASSWORD, auth_header, login, make_settings  # noqa: E402

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
        session = Session(bind=connection, join_transaction_mode="create_savepoint", **SESSION_OPTIONS)
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    """API client sharing `db_session`; everything is rolled back after the test.

    Like production (one session per request), whatever a request did not commit is discarded when it
    ends, so a service that forgets db.commit() fails the test instead of passing silently.
    """

    def _get_test_db() -> Iterator[Session]:
        try:
            yield db_session
        finally:
            db_session.rollback()  # create_savepoint mode: undoes only the uncommitted part

    app.dependency_overrides[get_db] = _get_test_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def override_settings() -> Iterator[Callable[..., Settings]]:
    """Replace settings injected via Depends(get_settings): override_settings(allow_registration=True)."""

    def _override(**changes) -> Settings:
        settings = make_settings(**changes)
        app.dependency_overrides[get_settings] = lambda: settings
        return settings

    yield _override
    app.dependency_overrides.pop(get_settings, None)


@pytest.fixture
def registration_open(override_settings: Callable[..., Settings]) -> Settings:
    return override_settings(allow_registration=True)


@pytest.fixture
def create_user(db_session: Session) -> Callable[..., User]:
    def _create(
        email: str = "ana@example.test", password: str = TEST_PASSWORD, rounds: int | None = None, **fields
    ) -> User:
        user = User(
            email=email,
            name=fields.pop("name", "Ana"),
            password_hash=hash_password(password, rounds or get_settings().bcrypt_rounds),
            **fields,
        )
        db_session.add(user)
        # Committed (to a savepoint) so it survives the per-request rollback of the `client` fixture.
        db_session.commit()
        return user

    return _create


@pytest.fixture
def authenticate(client: TestClient, create_user: Callable[..., User]) -> Callable[..., tuple[User, dict]]:
    """Create a user and log in through the API: `user, headers = authenticate("bia@example.test")`."""

    def _authenticate(email: str = "ana@example.test", **fields) -> tuple[User, dict[str, str]]:
        user = create_user(email=email, **fields)
        response = login(client, email, TEST_PASSWORD)
        assert response.status_code == 200, response.text
        return user, auth_header(response.json()["access_token"])

    return _authenticate


@pytest.fixture
def create_task(db_session: Session) -> Callable[..., Task]:
    """Insert a task straight into the database (committed to the test savepoint).

    Handy for fields the API does not accept, such as `created_at`: inside one test every row would
    otherwise get the same now() (it is the transaction start time).
    """

    def _create(user: User, title: str = "Tarefa", **fields) -> Task:
        if fields.get("status") == "done":
            fields.setdefault("completed_at", fields.get("created_at") or datetime.now(UTC))
        task = Task(user_id=user.id, title=title, **fields)
        db_session.add(task)
        db_session.commit()
        return task

    return _create
