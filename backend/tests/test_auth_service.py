import logging
import uuid

import jwt
import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.errors import ConflictError, ForbiddenError, UnauthorizedError
from app.core.security import DEFAULT_BCRYPT_ROUNDS, create_access_token, hash_password, hash_rounds
from app.models import User
from app.repositories import user as user_repo
from app.repositories.errors import DuplicateError, constraint_name, is_unique_violation
from app.schemas.user import UserCreate
from app.services import auth as auth_service
from tests.helpers import TEST_PASSWORD, make_settings

NEW_USER = UserCreate(email="Bia@Example.test", name="Bia", password="senha-forte")


@pytest.fixture
def open_settings():
    return make_settings(allow_registration=True)


# --- authenticate ---


def test_authenticate_returns_user_for_valid_credentials(db_session, create_user):
    user = create_user(email="ana@example.test")

    assert auth_service.authenticate(db_session, get_settings(), " ANA@example.test ", TEST_PASSWORD) is user


@pytest.mark.parametrize(
    ("email", "password", "user_fields"),
    [
        ("ana@example.test", "senha-errada", {}),
        ("ninguem@example.test", TEST_PASSWORD, {}),
        ("ana@example.test", TEST_PASSWORD, {"is_active": False}),
        ("ana@example.test", "senha-errada", {"is_active": False}),
        ("", TEST_PASSWORD, {}),
    ],
    ids=["wrong-password", "unknown-email", "inactive", "inactive-and-wrong-password", "empty-email"],
)
def test_authenticate_raises_invalid_credentials(db_session, create_user, email, password, user_fields):
    create_user(email="ana@example.test", **user_fields)

    with pytest.raises(auth_service.InvalidCredentials):
        auth_service.authenticate(db_session, get_settings(), email, password)


def test_authenticate_inactive_user_still_checks_password(db_session, create_user, monkeypatch):
    """Inactive accounts take the same time as active ones (the password is always checked)."""
    user = create_user(email="ana@example.test", is_active=False)
    calls = []
    monkeypatch.setattr(auth_service, "verify_password", lambda *args: calls.append(args) or True)

    with pytest.raises(auth_service.InvalidCredentials):
        auth_service.authenticate(db_session, get_settings(), "ana@example.test", TEST_PASSWORD)

    assert calls == [(TEST_PASSWORD, user.password_hash)]


@pytest.mark.parametrize("rounds", [4, 5])
def test_unknown_email_is_checked_against_hash_with_the_same_cost_as_real_users(
    db_session, monkeypatch, rounds
):
    settings = make_settings(allow_registration=True, bcrypt_rounds=rounds)
    user = auth_service.register(db_session, settings, NEW_USER)
    checked = []
    original = auth_service.verify_password
    monkeypatch.setattr(
        auth_service, "verify_password", lambda pw, hashed: checked.append(hashed) or original(pw, hashed)
    )

    with pytest.raises(auth_service.InvalidCredentials):
        auth_service.authenticate(db_session, settings, "ninguem@example.test", "senha-forte")

    assert [hash_rounds(h) for h in checked] == [hash_rounds(user.password_hash)] == [rounds]


def test_authenticate_with_nul_in_email_is_invalid_credentials(db_session, create_user):
    create_user(email="ana@example.test")

    with pytest.raises(auth_service.InvalidCredentials):
        auth_service.authenticate(db_session, get_settings(), "ana\x00@example.test", TEST_PASSWORD)


@pytest.mark.parametrize(
    "email",
    ["ana\x00@example.test", "ana\ud800@example.test", "sem-arroba"],
    ids=["nul", "surrogate", "invalid"],
)
def test_authenticate_with_unusable_email_checks_dummy_hash_and_fails(
    db_session, create_user, monkeypatch, email
):
    create_user(email="ana@example.test")
    checked = []
    original = auth_service.verify_password
    monkeypatch.setattr(
        auth_service, "verify_password", lambda pw, hashed: checked.append(hashed) or original(pw, hashed)
    )

    with pytest.raises(auth_service.InvalidCredentials):
        auth_service.authenticate(db_session, get_settings(), email, TEST_PASSWORD)

    assert checked == [auth_service.dummy_password_hash(get_settings().bcrypt_rounds)]


def test_successful_login_rehashes_password_with_configured_cost(db_session, create_user):
    user = create_user(email="ana@example.test")
    old_hash = user.password_hash
    assert hash_rounds(old_hash) == 4
    settings = make_settings(bcrypt_rounds=5)

    auth_service.authenticate(db_session, settings, "ana@example.test", TEST_PASSWORD)

    db_session.expire_all()
    stored = user_repo.get_by_email(db_session, "ana@example.test").password_hash
    assert stored != old_hash
    assert hash_rounds(stored) == 5
    assert auth_service.authenticate(db_session, settings, "ana@example.test", TEST_PASSWORD) is not None


def test_login_with_current_cost_does_not_rehash(db_session, create_user):
    user = create_user(email="ana@example.test")
    old_hash = user.password_hash

    auth_service.authenticate(db_session, get_settings(), "ana@example.test", TEST_PASSWORD)

    assert user.password_hash == old_hash


def test_failed_login_does_not_rehash(db_session, create_user):
    user = create_user(email="ana@example.test")
    old_hash = user.password_hash

    with pytest.raises(auth_service.InvalidCredentials):
        auth_service.authenticate(
            db_session, make_settings(bcrypt_rounds=5), "ana@example.test", "senha-errada"
        )

    assert user.password_hash == old_hash


def test_login_never_downgrades_a_stronger_hash(db_session, create_user):
    user = create_user(email="ana@example.test", rounds=5)
    old_hash = user.password_hash

    auth_service.authenticate(db_session, make_settings(bcrypt_rounds=4), "ana@example.test", TEST_PASSWORD)

    db_session.expire_all()
    assert user_repo.get_by_email(db_session, "ana@example.test").password_hash == old_hash
    assert hash_rounds(old_hash) == 5


def _stored_hash(db_session, user_id):
    return db_session.scalar(select(User.password_hash).where(User.id == user_id))


def test_rehash_keeps_a_hash_changed_concurrently(db_session, create_user, monkeypatch):
    user = create_user(email="ana@example.test")
    concurrent_hash = hash_password("senha-trocada-123", 4)
    original = auth_service.hash_password

    def hash_while_password_changes(password, rounds):
        # Another request changes the password between our read and our update.
        db_session.execute(
            update(User)
            .where(User.id == user.id)
            .values(password_hash=concurrent_hash)
            .execution_options(synchronize_session=False)
        )
        return original(password, rounds)

    monkeypatch.setattr(auth_service, "hash_password", hash_while_password_changes)

    result = auth_service.authenticate(
        db_session, make_settings(bcrypt_rounds=5), "ana@example.test", TEST_PASSWORD
    )

    assert result is user
    assert _stored_hash(db_session, user.id) == concurrent_hash


def test_rehash_of_user_deleted_during_login_does_not_fail(db_session, create_user, monkeypatch):
    user = create_user(email="ana@example.test")
    original = auth_service.hash_password

    def hash_while_user_is_deleted(password, rounds):
        db_session.execute(
            delete(User).where(User.id == user.id).execution_options(synchronize_session=False)
        )
        return original(password, rounds)

    monkeypatch.setattr(auth_service, "hash_password", hash_while_user_is_deleted)

    result = auth_service.authenticate(
        db_session, make_settings(bcrypt_rounds=5), "ana@example.test", TEST_PASSWORD
    )

    assert result is user
    assert _stored_hash(db_session, user.id) is None


def test_update_password_hash_is_compare_and_set(db_session, create_user):
    user = create_user(email="ana@example.test")
    old_hash = user.password_hash

    assert user_repo.update_password_hash(db_session, user.id, "outro-hash", "novo-hash") is False
    assert _stored_hash(db_session, user.id) == old_hash
    assert user_repo.update_password_hash(db_session, user.id, old_hash, "novo-hash") is True
    assert _stored_hash(db_session, user.id) == "novo-hash"
    assert user.password_hash == "novo-hash"  # the loaded object is synchronized too


@pytest.mark.parametrize("stored_hash", ["", "not-a-bcrypt-hash", "$2b$04$truncated"])
def test_corrupted_hash_is_invalid_credentials_and_logged(db_session, create_user, caplog, stored_hash):
    user = create_user(email="ana@example.test")
    user.password_hash = stored_hash
    db_session.flush()

    with (
        caplog.at_level(logging.WARNING, logger="app.services.auth"),
        pytest.raises(auth_service.InvalidCredentials),
    ):
        auth_service.authenticate(db_session, get_settings(), "ana@example.test", TEST_PASSWORD)

    assert [r.levelno for r in caplog.records] == [logging.WARNING]
    message = caplog.records[0].getMessage()
    assert str(user.id) in message
    assert TEST_PASSWORD not in message
    if stored_hash:
        assert stored_hash not in message


# --- register ---


def test_register_service_creates_active_user(db_session, open_settings):
    user = auth_service.register(db_session, open_settings, NEW_USER)

    assert user.id is not None
    assert user.email == "bia@example.test"
    assert user.is_active is True
    assert user.password_hash != "senha-forte"


def test_register_service_respects_allow_registration(db_session):
    settings = make_settings(allow_registration=False)

    with pytest.raises(auth_service.RegistrationDisabled):
        auth_service.register(db_session, settings, NEW_USER)


def test_register_service_rejects_existing_email_regardless_of_case(db_session, create_user, open_settings):
    create_user(email="BIA@example.test")

    with pytest.raises(auth_service.EmailAlreadyRegistered):
        auth_service.register(db_session, open_settings, NEW_USER)


def test_register_service_hashes_with_configured_cost(db_session):
    user = auth_service.register(
        db_session, make_settings(allow_registration=True, bcrypt_rounds=DEFAULT_BCRYPT_ROUNDS), NEW_USER
    )

    assert hash_rounds(user.password_hash) == DEFAULT_BCRYPT_ROUNDS


def test_register_reraises_integrity_errors_from_other_constraints(
    db_session, create_user, open_settings, monkeypatch
):
    existing = create_user(email="outra@example.test")
    db_session.expunge(existing)  # only the row stays, so the clash happens in Postgres, not in the session
    original_add = user_repo.add

    def add_with_duplicate_primary_key(db, user):
        user.id = existing.id
        return original_add(db, user)

    monkeypatch.setattr(user_repo, "add", add_with_duplicate_primary_key)

    with pytest.raises(DuplicateError) as exc_info:
        auth_service.register(db_session, open_settings, NEW_USER)

    assert not isinstance(exc_info.value, auth_service.EmailAlreadyRegistered)
    assert exc_info.value.constraint == "pk_users"
    assert isinstance(exc_info.value.__cause__, IntegrityError)


def test_constraint_name_reads_postgres_diagnostics(db_session, create_user):
    create_user(email="ana@example.test")

    with pytest.raises(IntegrityError) as exc_info:
        create_user(email="ANA@example.test")

    assert constraint_name(exc_info.value) == "uq_users_email_lower"
    assert is_unique_violation(exc_info.value)
    db_session.rollback()


def test_add_translates_unique_violation_into_duplicate_error(db_session, create_user):
    create_user(email="ana@example.test")

    with pytest.raises(DuplicateError) as exc_info:
        user_repo.add(db_session, User(email="ANA@example.test", name="Ana", password_hash="x"))

    assert exc_info.value.constraint == "uq_users_email_lower"
    db_session.rollback()


def test_add_lets_other_integrity_errors_through(db_session):
    with pytest.raises(IntegrityError) as exc_info:
        user_repo.add(db_session, User(email="ana@example.test", name=None, password_hash="x"))

    assert not is_unique_violation(exc_info.value)
    db_session.rollback()


# --- domain errors ---


@pytest.mark.parametrize(
    ("error", "family", "detail"),
    [
        (auth_service.RegistrationDisabled, ForbiddenError, "Cadastro desabilitado."),
        (auth_service.EmailAlreadyRegistered, ConflictError, "E-mail já cadastrado."),
        (auth_service.InvalidCredentials, UnauthorizedError, "E-mail ou senha inválidos."),
        (auth_service.NotAuthenticated, UnauthorizedError, "Não autenticado."),
    ],
)
def test_auth_errors_are_domain_errors_with_portuguese_detail(error, family, detail):
    exc = error()

    assert isinstance(exc, family)
    assert exc.detail == detail


# --- get_user_from_token ---


def test_get_user_from_token_returns_active_user(db_session, create_user):
    user = create_user()
    token = create_access_token(user.id, get_settings().secret_key, 5)

    assert auth_service.get_user_from_token(db_session, get_settings(), token) is user


@pytest.mark.parametrize("token", [None, "", "not-a-jwt"])
def test_get_user_from_token_rejects_missing_or_invalid_token(db_session, token):
    with pytest.raises(auth_service.NotAuthenticated):
        auth_service.get_user_from_token(db_session, get_settings(), token)


# --- get_active_user ---


def test_get_active_user(db_session, create_user):
    active = create_user(email="ana@example.test")
    inactive = create_user(email="inativa@example.test", is_active=False)

    assert auth_service.get_active_user(db_session, active.id) is active
    assert auth_service.get_active_user(db_session, inactive.id) is None
    assert auth_service.get_active_user(db_session, uuid.uuid4()) is None


# --- issue_access_token ---


def test_issue_access_token_uses_settings(create_user):
    user = create_user()
    settings = make_settings(secret_key="z" * 32, access_token_expire_minutes=45)

    token = auth_service.issue_access_token(settings, user)

    claims = jwt.decode(token, "z" * 32, algorithms=["HS256"])
    assert claims["sub"] == str(user.id)
    assert claims["exp"] - claims["iat"] == 45 * 60
