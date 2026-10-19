from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

from app.core.config import Settings, get_settings
from app.core.database import DbSession
from app.models import User
from app.services import auth as auth_service

SettingsDep = Annotated[Settings, Depends(get_settings)]

# auto_error=False so a missing token gets the same Portuguese 401 as an invalid one.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def get_current_user(
    db: DbSession, settings: SettingsDep, token: Annotated[str | None, Depends(oauth2_scheme)]
) -> User:
    return auth_service.get_user_from_token(db, settings, token)


CurrentUser = Annotated[User, Depends(get_current_user)]
