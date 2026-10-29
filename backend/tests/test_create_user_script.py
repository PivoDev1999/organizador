from contextlib import nullcontext

import pytest

from app.core.security import verify_password
from app.repositories import user as user_repo
from scripts import create_user
from tests.helpers import make_settings

EMAIL = "ana@casa.local"


def run(db_session, monkeypatch, *passwords: str) -> None:
    answers = iter(passwords)
    monkeypatch.setattr(create_user.getpass, "getpass", lambda prompt: next(answers))
    create_user.main(["--email", EMAIL, "--name", "Ana"], session_factory=lambda: nullcontext(db_session))


def test_creates_user_even_with_registration_closed(db_session, monkeypatch):
    monkeypatch.setattr(create_user, "get_settings", lambda: make_settings(allow_registration=False))

    run(db_session, monkeypatch, "s3nha-forte", "s3nha-forte")

    user = user_repo.get_by_email(db_session, EMAIL)
    assert user is not None and user.name == "Ana"
    assert verify_password("s3nha-forte", user.password_hash)


@pytest.mark.parametrize(
    ("passwords", "message"),
    [
        (("s3nha-forte", "outra-senha"), "as senhas não conferem"),
        (("curta", "curta"), "pelo menos 8 caracteres"),
    ],
)
def test_rejects_bad_password_without_echoing_it(db_session, monkeypatch, capsys, passwords, message):
    with pytest.raises(SystemExit) as exc:
        run(db_session, monkeypatch, *passwords)

    assert message in str(exc.value.code)
    assert passwords[0] not in str(exc.value.code)
    assert user_repo.get_by_email(db_session, EMAIL) is None
