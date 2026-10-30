from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

# Shared with the test fixture, so tests run with the same session behavior as the app.
SESSION_OPTIONS = {"autoflush": False, "expire_on_commit": False}

# hide_parameters: SQLAlchemy errors (and their tracebacks in the log) show the SQL without the values sent
# (e-mails, password hashes, notes...).
engine = create_engine(get_settings().database_url, pool_pre_ping=True, hide_parameters=True)
SessionLocal = sessionmaker(bind=engine, **SESSION_OPTIONS)


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


DbSession = Annotated[Session, Depends(get_db)]
