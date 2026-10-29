"""Create a household account from the server, without opening the public registration.

Usage (from backend/, or inside the container):
    python -m scripts.create_user --email ana@casa.local --name "Ana"
    docker compose exec api python -m scripts.create_user --email ana@casa.local --name "Ana"

The password is asked twice with getpass (never an argument: it would end up in the shell history and
in the process list). Same validation and hashing as POST /api/auth/register.
"""

import argparse
import getpass
import sys
from collections.abc import Callable
from contextlib import AbstractContextManager

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.schemas.user import UserCreate
from app.services import auth as auth_service
from app.services.auth import EmailAlreadyRegistered


def read_password() -> str:
    password = getpass.getpass("Senha: ")
    if getpass.getpass("Repita a senha: ") != password:
        sys.exit("Erro: as senhas não conferem.")
    return password


SessionFactory = Callable[[], AbstractContextManager[Session]]


def main(argv: list[str] | None = None, session_factory: SessionFactory | None = None) -> None:
    parser = argparse.ArgumentParser(description="Cria uma conta de usuário.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args(argv)

    try:
        data = UserCreate(email=args.email, name=args.name, password=read_password())
    except ValidationError as exc:
        # Only the messages: they never carry the value received (which may be the password).
        messages = "; ".join(str(error["msg"]).removeprefix("Value error, ") for error in exc.errors())
        sys.exit(f"Erro: {messages}")

    if session_factory is None:
        from app.core.database import SessionLocal

        session_factory = SessionLocal
    with session_factory() as session:
        try:
            user = auth_service.create_user(session, get_settings(), data)
        except EmailAlreadyRegistered as exc:
            sys.exit(f"Erro: {exc.detail}")
    print(f"Usuário criado: {user.email}")


if __name__ == "__main__":
    main()
