"""The dashboard reads everything in one REPEATABLE READ, READ ONLY transaction.

A bill paid by another device while the dashboard is being built must not show up both as "to pay"
(`finance.upcoming`) and as paid in the month's totals. Under READ COMMITTED each query would take a
new snapshot and the month totals (read after the bills) would already see the payment.

Like tests/test_finance_concurrency.py, this needs real transactions: it commits to the test database
through `SessionLocal`, calls the real app (no `get_db` override) and deletes what it created at the end.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, text

from app.core import clock
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.main import app
from app.models import Transaction, User
from app.repositories import snapshot as snapshot_repo
from app.services import transaction as transaction_service
from tests.helpers import auth_header, make_settings, make_token

URL = "/api/dashboard"
NOW = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)  # 12:00 in São Paulo
# Strict, like production (the suite turns it off for its savepoint-based session).
SETTINGS = make_settings(dashboard_require_snapshot=True)


@pytest.fixture
def committed(monkeypatch) -> Iterator[tuple[uuid.UUID, uuid.UUID]]:
    """A real user with one pending bill due today. Yields (user_id, transaction_id)."""
    monkeypatch.setattr(clock, "now_utc", lambda: NOW)
    with SessionLocal() as db:
        user = User(
            email=f"race-{uuid.uuid4().hex}@example.test", name="Race", password_hash=hash_password("x", 4)
        )
        db.add(user)
        db.flush()
        bill = Transaction(
            user_id=user.id,
            type="expense",
            amount=Decimal("189.90"),
            category="Casa",
            due_date=date(2026, 10, 21),
        )
        db.add(bill)
        db.commit()
        ids = (user.id, bill.id)
    yield ids
    with SessionLocal() as db:
        db.execute(delete(User).where(User.id == ids[0]))  # cascades to everything
        db.commit()


def test_bill_paid_while_the_dashboard_is_built_is_never_in_both_states(committed, monkeypatch):
    user_id, bill_id = committed
    read_month_totals = transaction_service.get_month_totals
    seen: dict[str, str] = {}

    def pay_meanwhile(db, *args):
        # Runs after the bills to pay were read and before the month totals are.
        seen["isolation"] = db.scalar(text("SHOW transaction_isolation"))
        seen["read_only"] = db.scalar(text("SHOW transaction_read_only"))
        with SessionLocal() as other_device:
            transaction_service.pay(other_device, SETTINGS, user_id, bill_id, None)  # commits
        return read_month_totals(db, *args)

    applied: list[bool] = []
    begin_read_snapshot = snapshot_repo.begin_read_snapshot

    def spy(db, **kwargs):
        applied.append(begin_read_snapshot(db, **kwargs))
        return applied[-1]

    monkeypatch.setattr(snapshot_repo, "begin_read_snapshot", spy)
    monkeypatch.setattr(transaction_service, "get_month_totals", pay_meanwhile)
    monkeypatch.setitem(app.dependency_overrides, get_settings, lambda: SETTINGS)
    headers = auth_header(make_token(user_id))
    with TestClient(app) as client:
        during = client.get(URL, headers=headers)
        monkeypatch.setattr(transaction_service, "get_month_totals", read_month_totals)
        after = client.get(URL, headers=headers)

    assert during.status_code == 200, during.text
    finance = during.json()["finance"]
    assert [item["id"] for item in finance["upcoming"]["items"]] == [str(bill_id)]
    assert finance["month"]["expense"] == {"total": "189.90", "paid": "0.00", "pending": "189.90"}
    # The payment did commit: the next dashboard shows it, again in both places.
    finance = after.json()["finance"]
    assert finance["upcoming"] == {"items": [], "total": 0}
    assert finance["month"]["expense"] == {"total": "189.90", "paid": "189.90", "pending": "0.00"}
    assert seen == {"isolation": "repeatable read", "read_only": "on"}
    assert applied == [True, True]
