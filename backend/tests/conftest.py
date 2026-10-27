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
# The `db_session` fixture runs inside savepoints, where the dashboard cannot set its REPEATABLE READ
# snapshot; production keeps it required. tests/test_dashboard_concurrency.py turns it back on.
os.environ["DASHBOARD_REQUIRE_SNAPSHOT"] = "false"
get_settings.cache_clear()

import uuid  # noqa: E402
from collections.abc import Callable, Iterator  # noqa: E402
from datetime import UTC, date, datetime  # noqa: E402
from decimal import Decimal  # noqa: E402
from pathlib import Path  # noqa: E402

from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from alembic import command  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.core.database import SESSION_OPTIONS, engine, get_db  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.core.storage import get_storage  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    PantryItem,
    Pet,
    PetEvent,
    Routine,
    ShoppingItem,
    Task,
    Transaction,
    User,
)
from app.models.file import FileEntityType  # noqa: E402
from tests.fakes import FakeStorage  # noqa: E402
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
def storage() -> FakeStorage:
    """In-memory file storage; the `client` fixture injects it in place of Garage."""
    return FakeStorage()


@pytest.fixture
def client(db_session: Session, storage: FakeStorage) -> Iterator[TestClient]:
    """API client sharing `db_session`; everything is rolled back after the test.

    Like production (one session per request), whatever a request did not commit is discarded when it
    ends, so a service that forgets db.commit() fails the test instead of passing silently.
    Files go to the `storage` fixture (FakeStorage), never to Garage.
    """

    def _get_test_db() -> Iterator[Session]:
        try:
            yield db_session
        finally:
            db_session.rollback()  # create_savepoint mode: undoes only the uncommitted part

    app.dependency_overrides[get_db] = _get_test_db
    app.dependency_overrides[get_storage] = lambda: storage
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


@pytest.fixture
def make_entity(db_session: Session) -> Callable[..., uuid.UUID]:
    """Insert a record of any attachable type for the user and return its id: make_entity(ana, "pet").

    `pet_id` links a "pet_event" (a new pet is created when it is omitted) or a "transaction"; other
    fields go to the model (e.g. is_purchased=True for a shopping item).
    """

    def _make(user: User, entity_type: str, pet_id: uuid.UUID | None = None, **fields) -> uuid.UUID:
        uid = user.id
        match FileEntityType(entity_type):
            case FileEntityType.TASK:
                record = Task(user_id=uid, title="Tarefa", **fields)
            case FileEntityType.ROUTINE:
                record = Routine(user_id=uid, name="Rotina", frequency="daily", **fields)
            case FileEntityType.PANTRY_ITEM:
                record = PantryItem(user_id=uid, name=f"Arroz {uuid.uuid4()}", category="Grãos", unit="kg")
            case FileEntityType.SHOPPING_ITEM:
                record = ShoppingItem(user_id=uid, name="Leite", category="Laticínios", **fields)
            case FileEntityType.PET:
                record = Pet(user_id=uid, name="Mel", species="Cachorro", **fields)
            case FileEntityType.PET_EVENT:
                pet_id = pet_id or _make(user, FileEntityType.PET)
                record = PetEvent(pet_id=pet_id, user_id=uid, type="vet", occurred_on=date(2026, 1, 10))
            case FileEntityType.TRANSACTION:
                record = Transaction(
                    user_id=uid,
                    type="expense",
                    amount=Decimal("10.00"),
                    category="Casa",
                    due_date=date(2026, 1, 1),
                    pet_id=pet_id,
                )
        db_session.add(record)
        db_session.commit()
        return record.id

    return _make
