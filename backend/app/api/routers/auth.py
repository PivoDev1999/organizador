from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import CurrentUser, SettingsDep
from app.core.database import DbSession
from app.schemas.auth import Token
from app.schemas.user import UserCreate, UserRead
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, db: DbSession, settings: SettingsDep) -> UserRead:
    return UserRead.model_validate(auth_service.register(db, settings, data))


@router.post("/login")
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession, settings: SettingsDep
) -> Token:
    user = auth_service.authenticate(db, settings, form.username, form.password)
    return Token(access_token=auth_service.issue_access_token(settings, user))


@router.get("/me")
def me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)
