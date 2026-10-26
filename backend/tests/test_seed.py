import bcrypt
import pytest
from sqlalchemy import func, select

from app.core import clock
from app.core.config import get_settings
from app.models import (
    Budget,
    PantryItem,
    Pet,
    PetEvent,
    Routine,
    RoutineLog,
    ShoppingItem,
    Task,
    Transaction,
    User,
)
from scripts.seed import DEMO_EMAIL, SeedError, seed
from tests.helpers import make_settings

EXPECTED_COUNTS = {
    Task: 7,
    Routine: 7,
    RoutineLog: 8,
    PantryItem: 8,
    ShoppingItem: 7,
    Pet: 2,
    PetEvent: 7,
    Transaction: 10,
    Budget: 6,
}


def _count(session, model, user_id):
    return session.scalar(select(func.count()).select_from(model).where(model.user_id == user_id))


def test_seed_is_idempotent(db_session):
    seed(db_session, password="test-password")
    user = seed(db_session, password="test-password")

    demo_users = db_session.scalar(
        select(func.count()).select_from(User).where(func.lower(User.email) == DEMO_EMAIL)
    )
    assert demo_users == 1
    assert bcrypt.checkpw(b"test-password", user.password_hash.encode())
    for model, expected in EXPECTED_COUNTS.items():
        assert _count(db_session, model, user.id) == expected, model.__tablename__


def test_seed_links_pet_expenses_and_low_stock_shopping_items(db_session):
    user = seed(db_session, password="test-password")

    pet_expenses = db_session.scalars(
        select(Transaction).where(Transaction.user_id == user.id, Transaction.pet_id.is_not(None))
    ).all()
    assert pet_expenses and all(tx.category == "Pets" for tx in pet_expenses)
    # Accrual basis: every sample transaction falls in the current month, and budgets use its categories.
    transactions = db_session.scalars(select(Transaction).where(Transaction.user_id == user.id)).all()
    budgets = db_session.scalars(select(Budget).where(Budget.user_id == user.id)).all()
    month = clock.today(get_settings().timezone).replace(day=1)
    assert {(tx.due_date.year, tx.due_date.month) for tx in transactions} == {(month.year, month.month)}
    assert {budget.month for budget in budgets} == {month}
    expense_categories = {tx.category for tx in transactions if tx.type == "expense"}
    assert expense_categories <= {budget.category for budget in budgets}

    linked = db_session.scalars(
        select(ShoppingItem).where(ShoppingItem.user_id == user.id, ShoppingItem.pantry_item_id.is_not(None))
    ).all()
    assert linked
    for item in linked:
        assert item.pantry_item.quantity < item.pantry_item.min_quantity


@pytest.mark.parametrize("password", [None, "", "change-me"])
def test_seed_requires_real_password(db_session, password):
    settings = make_settings(seed_user_password=password)

    with pytest.raises(SeedError, match="SEED_USER_PASSWORD"):
        seed(db_session, settings=settings)
