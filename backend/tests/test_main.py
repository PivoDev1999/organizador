import logging

import pytest

from app.core.security import DEFAULT_BCRYPT_ROUNDS
from app.main import WEAK_BCRYPT_ROUNDS, prepare_password_hashing
from tests.helpers import make_settings


@pytest.mark.parametrize("rounds", [4, WEAK_BCRYPT_ROUNDS - 1])
def test_warns_when_bcrypt_rounds_is_weak(caplog, rounds):
    with caplog.at_level(logging.WARNING, logger="app.main"):
        prepare_password_hashing(make_settings(bcrypt_rounds=rounds))

    assert [r.levelno for r in caplog.records] == [logging.WARNING]
    assert f"BCRYPT_ROUNDS={rounds}" in caplog.records[0].getMessage()


@pytest.mark.parametrize("rounds", [WEAK_BCRYPT_ROUNDS, DEFAULT_BCRYPT_ROUNDS])
def test_does_not_warn_for_production_cost(caplog, rounds):
    with caplog.at_level(logging.WARNING, logger="app.main"):
        prepare_password_hashing(make_settings(bcrypt_rounds=rounds))

    assert caplog.records == []
