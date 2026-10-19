import logging
import uuid

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ConflictError, ForbiddenError, UnauthorizedError
from app.core.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    dummy_password_hash,
    hash_password,
    hash_rounds,
    verify_password,
)
from app.core.text import parse_email
from app.models import User
from app.models.user import EMAIL_UNIQUE_INDEX
from app.repositories import user as user_repo
from app.repositories.errors import DuplicateError
from app.schemas.user import UserCreate

logger = logging.getLogger(__name__)


class RegistrationDisabled(ForbiddenError):
    detail = "Cadastro desabilitado."


class EmailAlreadyRegistered(ConflictError):
    detail = "E-mail já cadastrado."


class InvalidCredentials(UnauthorizedError):
    detail = "E-mail ou senha inválidos."


class NotAuthenticated(UnauthorizedError):
    detail = "Não autenticado."


def register(db: Session, settings: Settings, data: UserCreate) -> User:
    if not settings.allow_registration:
        raise RegistrationDisabled
    if user_repo.get_by_email(db, data.email) is not None:
        raise EmailAlreadyRegistered

    user = User(
        email=data.email,
        name=data.name,
        password_hash=hash_password(data.password, settings.bcrypt_rounds),
    )
    try:
        user_repo.add(db, user)
    except DuplicateError as exc:
        db.rollback()
        # Lost a race with a concurrent registration: the unique index on lower(email) decides.
        if exc.constraint == EMAIL_UNIQUE_INDEX:
            raise EmailAlreadyRegistered from exc
        raise
    db.commit()
    return user


def authenticate(db: Session, settings: Settings, email: str, password: str) -> User:
    try:
        user = user_repo.get_by_email(db, parse_email(email))
    except ValueError:
        user = None
    if user is None:
        # Same bcrypt work as a real check, so timing does not reveal whether the e-mail exists.
        verify_password(password, dummy_password_hash(settings.bcrypt_rounds))
        raise InvalidCredentials

    try:
        valid = verify_password(password, user.password_hash)
    except ValueError:
        logger.warning("Malformed password hash for user %s", user.id)
        raise InvalidCredentials from None
    if not valid or not user.is_active:
        raise InvalidCredentials

    # Only upgrade: a lower configured cost (e.g. a test setting) must never weaken stored hashes.
    if hash_rounds(user.password_hash) < settings.bcrypt_rounds:
        new_hash = hash_password(password, settings.bcrypt_rounds)
        # Compare-and-set: if the hash changed meanwhile (or the user is gone), keep it and log in anyway.
        user_repo.update_password_hash(db, user.id, user.password_hash, new_hash)
        db.commit()
    return user


def issue_access_token(settings: Settings, user: User) -> str:
    return create_access_token(user.id, settings.secret_key, settings.access_token_expire_minutes)


def get_active_user(db: Session, user_id: uuid.UUID) -> User | None:
    user = user_repo.get_by_id(db, user_id)
    return user if user is not None and user.is_active else None


def get_user_from_token(db: Session, settings: Settings, token: str | None) -> User:
    if not token:
        raise NotAuthenticated
    try:
        user_id = decode_access_token(token, settings.secret_key)
    except InvalidTokenError:
        raise NotAuthenticated from None
    user = get_active_user(db, user_id)
    if user is None:
        raise NotAuthenticated
    return user
