from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import CheckConstraint, delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Base,
    Budget,
    File,
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

TODAY = date(2026, 10, 19)
NOW = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)


def make_user(session: Session, email: str) -> User:
    user = User(email=email, name="Ana", password_hash="not-a-real-hash")
    insert_ok(session, user)
    return user


def insert_ok(session: Session, obj: Any) -> Any:
    session.add(obj)
    session.flush()
    return obj


def assert_violates(session: Session, obj: Any, constraint: str) -> None:
    """Insert `obj` inside a savepoint and assert that the named constraint rejects it."""
    with pytest.raises(IntegrityError) as exc_info, session.begin_nested():
        session.add(obj)
        session.flush()
    assert exc_info.value.orig.diag.constraint_name == constraint


@pytest.fixture
def user(db_session: Session) -> User:
    return make_user(db_session, "ana@example.com")


@pytest.fixture
def other_user(db_session: Session) -> User:
    return make_user(db_session, "bia@example.com")


# Factories: a valid row of each table (parents are inserted on the fly), with fields overridable.


def new_task(session: Session, user: User, **fields) -> Task:
    return Task(**{"user_id": user.id, "title": "Varrer a casa", **fields})


def new_routine(session: Session, user: User, **fields) -> Routine:
    return Routine(**{"user_id": user.id, "name": "Passear", "frequency": "daily", **fields})


def new_routine_log(session: Session, user: User, **fields) -> RoutineLog:
    routine = insert_ok(session, new_routine(session, user))
    return RoutineLog(**{"routine_id": routine.id, "user_id": user.id, "done_on": TODAY, **fields})


def new_pantry_item(session: Session, user: User, **fields) -> PantryItem:
    return PantryItem(**{"user_id": user.id, "name": "Arroz", "category": "Grãos", "unit": "kg", **fields})


def new_shopping_item(session: Session, user: User, **fields) -> ShoppingItem:
    return ShoppingItem(**{"user_id": user.id, "name": "Arroz", "category": "Grãos", **fields})


def new_pet(session: Session, user: User, **fields) -> Pet:
    return Pet(**{"user_id": user.id, "name": "Mel", "species": "Cachorro", **fields})


def new_pet_event(session: Session, user: User, **fields) -> PetEvent:
    pet = insert_ok(session, new_pet(session, user))
    return PetEvent(**{"pet_id": pet.id, "user_id": user.id, "type": "vet", "occurred_on": TODAY, **fields})


def new_transaction(session: Session, user: User, **fields) -> Transaction:
    defaults = {"type": "expense", "amount": Decimal("10.00"), "category": "Moradia", "due_date": TODAY}
    return Transaction(**{"user_id": user.id, **defaults, **fields})


def new_budget(session: Session, user: User, **fields) -> Budget:
    defaults = {"category": "Pets", "month": date(2026, 10, 1), "amount": Decimal("100.00")}
    return Budget(**{"user_id": user.id, **defaults, **fields})


def new_file(session: Session, user: User, **fields) -> File:
    defaults = {
        "entity_type": "task",
        "entity_id": user.id,
        "bucket": "organizador",
        "object_key": "a/b.pdf",
        "original_name": "b.pdf",
        "content_type": "application/pdf",
        "size_bytes": 10,
    }
    return File(**{"user_id": user.id, **defaults, **fields})


Factory = Callable[..., Any]

CHECK_VIOLATIONS: list[tuple[Factory, dict[str, Any], str]] = [
    (new_task, {"status": "archived"}, "ck_tasks_status"),
    (new_task, {"priority": "urgent"}, "ck_tasks_priority"),
    (new_task, {"status": "done"}, "ck_tasks_completed_at_matches_status"),
    (new_task, {"status": "doing", "completed_at": NOW}, "ck_tasks_completed_at_matches_status"),
    (new_routine, {"frequency": "yearly"}, "ck_routines_frequency"),
    (new_routine, {"frequency": "weekly"}, "ck_routines_schedule_matches_frequency"),
    (new_routine, {"frequency": "weekly", "days_of_week": []}, "ck_routines_schedule_matches_frequency"),
    (
        new_routine,
        {"frequency": "weekly", "days_of_week": [1], "day_of_month": 10},
        "ck_routines_schedule_matches_frequency",
    ),
    (new_routine, {"frequency": "monthly"}, "ck_routines_schedule_matches_frequency"),
    (
        new_routine,
        {"frequency": "monthly", "day_of_month": 10, "days_of_week": [1]},
        "ck_routines_schedule_matches_frequency",
    ),
    (new_routine, {"frequency": "daily", "day_of_month": 10}, "ck_routines_schedule_matches_frequency"),
    (new_routine, {"frequency": "daily", "days_of_week": [1]}, "ck_routines_schedule_matches_frequency"),
    (new_routine, {"frequency": "monthly", "day_of_month": 32}, "ck_routines_day_of_month_range"),
    (new_routine, {"frequency": "monthly", "day_of_month": 0}, "ck_routines_day_of_month_range"),
    (new_routine, {"frequency": "weekly", "days_of_week": [1, 7]}, "ck_routines_days_of_week_range"),
    (new_routine, {"frequency": "weekly", "days_of_week": [-1]}, "ck_routines_days_of_week_range"),
    (
        new_routine,
        {"frequency": "weekly", "days_of_week": [[1, 2], [3, 4]]},
        "ck_routines_days_of_week_one_dimension",
    ),
    (new_pantry_item, {"quantity": Decimal("-1")}, "ck_pantry_items_quantity_non_negative"),
    (new_pantry_item, {"min_quantity": Decimal("-0.5")}, "ck_pantry_items_min_quantity_non_negative"),
    (new_shopping_item, {"quantity": Decimal("0")}, "ck_shopping_items_quantity_positive"),
    (
        new_shopping_item,
        {"estimated_price": Decimal("-0.01")},
        "ck_shopping_items_estimated_price_non_negative",
    ),
    (new_shopping_item, {"is_purchased": True}, "ck_shopping_items_purchased_at_matches_is_purchased"),
    (
        new_shopping_item,
        {"is_purchased": False, "purchased_at": NOW},
        "ck_shopping_items_purchased_at_matches_is_purchased",
    ),
    (new_pet, {"weight_kg": Decimal("0")}, "ck_pets_weight_kg_positive"),
    (new_pet_event, {"type": "bath"}, "ck_pet_events_type"),
    (new_pet_event, {"next_due_on": date(2026, 10, 18)}, "ck_pet_events_next_due_after_occurred"),
    (new_transaction, {"type": "transfer"}, "ck_transactions_type"),
    (new_transaction, {"amount": Decimal("0")}, "ck_transactions_amount_positive"),
    (new_transaction, {"amount": Decimal("-10.00")}, "ck_transactions_amount_positive"),
    (new_budget, {"month": date(2026, 10, 15)}, "ck_budgets_month_first_day"),
    (new_budget, {"amount": Decimal("-1.00")}, "ck_budgets_amount_non_negative"),
    (new_file, {"entity_type": "budget"}, "ck_files_entity_type"),
    (new_file, {"size_bytes": -1}, "ck_files_size_bytes_non_negative"),
]

VALID_ROWS: list[tuple[Factory, dict[str, Any]]] = [
    (new_task, {}),
    (new_task, {"status": "done", "completed_at": NOW}),
    (new_routine, {"frequency": "daily"}),
    (new_routine, {"frequency": "weekly", "days_of_week": [0, 6]}),
    (new_routine, {"frequency": "weekly", "days_of_week": [3]}),
    (new_routine, {"frequency": "monthly", "day_of_month": 1}),
    (new_routine, {"frequency": "monthly", "day_of_month": 31}),
    (new_routine_log, {}),
    (new_pantry_item, {"quantity": Decimal("0"), "min_quantity": Decimal("0")}),
    (new_shopping_item, {"quantity": Decimal("0.5"), "estimated_price": Decimal("0")}),
    (new_shopping_item, {"is_purchased": True, "purchased_at": NOW}),
    (new_pet, {"weight_kg": Decimal("0.01")}),
    (new_pet_event, {"next_due_on": TODAY}),
    (new_transaction, {"type": "income", "amount": Decimal("0.01")}),
    (new_budget, {"amount": Decimal("0")}),
    (new_file, {"size_bytes": 0}),
]


def _case_id(case: tuple) -> str:
    return f"{case[0].__name__.removeprefix('new_')}-{case[-1] if isinstance(case[-1], str) else case[1]}"


@pytest.mark.parametrize(
    ("factory", "fields", "constraint"), CHECK_VIOLATIONS, ids=map(_case_id, CHECK_VIOLATIONS)
)
def test_check_constraint_rejects_invalid_value(db_session, user, factory, fields, constraint):
    assert_violates(db_session, factory(db_session, user, **fields), constraint)


@pytest.mark.parametrize(("factory", "fields"), VALID_ROWS, ids=map(_case_id, VALID_ROWS))
def test_valid_rows_are_accepted(db_session, user, factory, fields):
    insert_ok(db_session, factory(db_session, user, **fields))


def test_every_check_constraint_has_a_violation_case():
    declared = {
        str(constraint.name)
        for table in Base.metadata.tables.values()
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert declared == {constraint for _, _, constraint in CHECK_VIOLATIONS}


def test_task_defaults(db_session, user):
    task = insert_ok(db_session, new_task(db_session, user))
    db_session.refresh(task)
    assert (task.status, task.priority) == ("todo", "medium")
    assert task.id is not None and task.created_at is not None


class TestUnique:
    def test_email_ignores_case(self, db_session, user):
        duplicate = User(email="ANA@Example.com", name="Outra Ana", password_hash="x")
        assert_violates(db_session, duplicate, "uq_users_email_lower")

    def test_budget_per_category_and_month(self, db_session, user):
        insert_ok(db_session, new_budget(db_session, user))
        assert_violates(db_session, new_budget(db_session, user), "uq_budgets_user_id_category_month")

    def test_routine_log_per_day(self, db_session, user):
        log = insert_ok(db_session, new_routine_log(db_session, user))
        duplicate = RoutineLog(routine_id=log.routine_id, user_id=user.id, done_on=log.done_on)
        assert_violates(db_session, duplicate, "uq_routine_logs_routine_id_done_on")
        insert_ok(
            db_session, RoutineLog(routine_id=log.routine_id, user_id=user.id, done_on=date(2026, 10, 20))
        )

    def test_file_object_key_per_bucket(self, db_session, user):
        insert_ok(db_session, new_file(db_session, user))
        assert_violates(db_session, new_file(db_session, user), "uq_files_bucket_object_key")
        insert_ok(db_session, new_file(db_session, user, bucket="outro-bucket"))


class TestOwnership:
    """Composite FKs: a child row must belong to the same user as its parent."""

    def test_routine_log_cannot_point_to_another_users_routine(self, db_session, user, other_user):
        routine = insert_ok(db_session, new_routine(db_session, other_user))
        log = RoutineLog(routine_id=routine.id, user_id=user.id, done_on=TODAY)
        assert_violates(db_session, log, "fk_routine_logs_routine_id_routines")

    def test_pet_event_cannot_point_to_another_users_pet(self, db_session, user, other_user):
        pet = insert_ok(db_session, new_pet(db_session, other_user))
        event = PetEvent(pet_id=pet.id, user_id=user.id, type="vet", occurred_on=TODAY)
        assert_violates(db_session, event, "fk_pet_events_pet_id_pets")

    def test_transaction_cannot_point_to_another_users_pet(self, db_session, user, other_user):
        pet = insert_ok(db_session, new_pet(db_session, other_user))
        tx = new_transaction(db_session, user, pet_id=pet.id)
        assert_violates(db_session, tx, "fk_transactions_pet_id_pets")

    def test_shopping_item_cannot_point_to_another_users_pantry_item(self, db_session, user, other_user):
        pantry = insert_ok(db_session, new_pantry_item(db_session, other_user))
        item = new_shopping_item(db_session, user, pantry_item_id=pantry.id)
        assert_violates(db_session, item, "fk_shopping_items_pantry_item_id_pantry_items")


class TestOnDelete:
    def test_deleting_pet_removes_events_and_unlinks_transactions(self, db_session, user):
        pet = insert_ok(db_session, new_pet(db_session, user))
        event = insert_ok(db_session, PetEvent(pet_id=pet.id, user_id=user.id, type="vet", occurred_on=TODAY))
        tx = insert_ok(db_session, new_transaction(db_session, user, pet_id=pet.id))
        event_id, tx_id = event.id, tx.id
        db_session.expunge_all()

        db_session.execute(delete(Pet).where(Pet.id == pet.id))

        assert db_session.get(PetEvent, event_id) is None
        tx = db_session.get(Transaction, tx_id)
        assert tx.pet_id is None
        assert tx.user_id == user.id

    def test_deleting_routine_removes_its_logs(self, db_session, user):
        log = insert_ok(db_session, new_routine_log(db_session, user))
        routine_id = log.routine_id
        db_session.expunge_all()

        db_session.execute(delete(Routine).where(Routine.id == routine_id))

        remaining = db_session.scalar(select(func.count()).where(RoutineLog.routine_id == routine_id))
        assert remaining == 0

    def test_deleting_pantry_item_unlinks_shopping_items(self, db_session, user):
        pantry = insert_ok(db_session, new_pantry_item(db_session, user))
        item = insert_ok(db_session, new_shopping_item(db_session, user, pantry_item_id=pantry.id))
        item_id = item.id
        db_session.expunge_all()

        db_session.execute(delete(PantryItem).where(PantryItem.id == pantry.id))

        item = db_session.get(ShoppingItem, item_id)
        assert item.pantry_item_id is None
        assert item.user_id == user.id

    def test_deleting_user_removes_only_their_data(self, db_session, other_user):
        from scripts.seed import seed

        demo = seed(db_session, password="test-password")
        insert_ok(db_session, new_task(db_session, other_user))
        insert_ok(db_session, new_file(db_session, demo))
        demo_id = demo.id
        db_session.expunge_all()

        db_session.execute(delete(User).where(User.id == demo_id))

        for model in (
            Task,
            Routine,
            RoutineLog,
            PantryItem,
            ShoppingItem,
            Pet,
            PetEvent,
            Transaction,
            Budget,
            File,
        ):
            remaining = db_session.scalar(select(func.count()).where(model.user_id == demo_id))
            assert remaining == 0, model.__tablename__
        assert db_session.scalar(select(func.count()).where(Task.user_id == other_user.id)) == 1


class TestUpdatedAt:
    OLD = datetime(2020, 1, 1, tzinfo=UTC)

    def test_trigger_updates_on_raw_sql(self, db_session, user):
        task = insert_ok(db_session, new_task(db_session, user, created_at=self.OLD, updated_at=self.OLD))

        db_session.execute(
            text("UPDATE tasks SET title = 'Varrer o quintal' WHERE id = :id"), {"id": task.id}
        )

        updated_at = db_session.scalar(text("SELECT updated_at FROM tasks WHERE id = :id"), {"id": task.id})
        assert updated_at == db_session.scalar(text("SELECT now()"))
        assert updated_at > self.OLD

    def test_orm_reads_value_set_by_trigger(self, db_session, user):
        task = insert_ok(db_session, new_task(db_session, user, created_at=self.OLD, updated_at=self.OLD))

        task.title = "Varrer o quintal"
        db_session.flush()

        assert task.updated_at == db_session.scalar(text("SELECT now()"))
        assert task.created_at == self.OLD
