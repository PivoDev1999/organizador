"""GET /api/calendar?from=&to=: events, open tasks, pending bills and pet reminders of a range, read only."""

from datetime import UTC, date, datetime, time
from decimal import Decimal

import pytest

from app.core import agenda
from app.models import Event, Pet, PetEvent, Task, Transaction
from app.repositories.snapshot import SnapshotUnavailableError

URL = "/api/calendar"
RANGE = {"from": "2026-11-01", "to": "2026-11-30"}
D = date.fromisoformat


@pytest.fixture
def ana(authenticate):
    return authenticate("ana@example.test")


@pytest.fixture
def bia(authenticate):
    return authenticate("bia@example.test")


@pytest.fixture
def add(db_session):
    def _add(row):
        db_session.add(row)
        db_session.commit()
        return row

    return _add


@pytest.fixture
def get(client):
    def _get(headers, params=RANGE) -> list[dict]:
        response = client.get(URL, params=params, headers=headers)
        assert response.status_code == 200, response.text
        return response.json()

    return _get


def summary(items: list[dict]) -> list[tuple]:
    return [(item["kind"], item["date"], item["time"], item["title"]) for item in items]


def test_each_kind_with_its_fields_ordered_by_date_then_time(ana, add, get):
    user, headers = ana
    uid = user.id
    event = add(
        Event(
            user_id=uid,
            title="Dentista",
            starts_on=D("2026-11-10"),
            start_time=time(14, 0),
            end_time=time(15, 0),
            location="Centro",
        )
    )
    add(
        Event(
            user_id=uid,
            title="Feira",
            starts_on=D("2026-11-07"),
            recurrence="weekly",
            repeat_until=D("2026-11-14"),
        )
    )
    task = add(Task(user_id=uid, title="Pagar IPVA", due_date=D("2026-11-10"), priority="high"))
    bill = add(
        Transaction(
            user_id=uid, type="expense", amount=Decimal("120.50"), category="Casa", due_date=D("2026-11-10")
        )
    )
    add(
        Transaction(
            user_id=uid,
            type="expense",
            amount=Decimal("80.00"),
            category="Saúde",
            description="Farmácia",
            due_date=D("2026-11-20"),
        )
    )
    mel = add(Pet(user_id=uid, name="Mel", species="Cachorro"))
    reminder = add(
        PetEvent(
            pet_id=mel.id,
            user_id=uid,
            type="vaccine",
            description="V10",
            occurred_on=D("2025-11-12"),
            next_due_on=D("2026-11-12"),
        )
    )

    items = get(headers)

    assert summary(items) == [
        ("event", "2026-11-07", None, "Feira"),
        ("task", "2026-11-10", None, "Pagar IPVA"),
        ("bill", "2026-11-10", None, "Casa"),  # no description: the category
        ("event", "2026-11-10", "14:00:00", "Dentista"),
        ("pet", "2026-11-12", None, "Mel"),
        ("event", "2026-11-14", None, "Feira"),
        ("bill", "2026-11-20", None, "Farmácia"),
    ]
    by_kind = {item["kind"]: item for item in items if item["date"] in ("2026-11-10", "2026-11-12")}
    assert by_kind["event"] == {
        "kind": "event",
        "id": str(event.id),
        "date": "2026-11-10",
        "time": "14:00:00",
        "title": "Dentista",
        "end_time": "15:00:00",
        "location": "Centro",
        "recurrence": "none",
    }
    assert (by_kind["task"]["id"], by_kind["task"]["status"], by_kind["task"]["priority"]) == (
        str(task.id),
        "todo",
        "high",
    )
    assert (by_kind["bill"]["id"], by_kind["bill"]["amount"], by_kind["bill"]["category"]) == (
        str(bill.id),
        "120.50",
        "Casa",
    )
    assert by_kind["pet"] == {
        "kind": "pet",
        "id": str(reminder.id),
        "date": "2026-11-12",
        "time": None,
        "title": "Mel",
        "pet_id": str(mel.id),
        "pet_name": "Mel",
        "type": "vaccine",
        "description": "V10",
    }


def test_leaves_out_done_tasks_paid_bills_income_old_series_and_dates_outside_the_range(ana, add, get):
    user, headers = ana
    uid = user.id
    paid = datetime(2026, 11, 2, tzinfo=UTC)
    add(Task(user_id=uid, title="Feita", due_date=D("2026-11-05"), status="done", completed_at=paid))
    add(Task(user_id=uid, title="Fora", due_date=D("2026-12-01")))
    add(Task(user_id=uid, title="Sem prazo"))
    expense = {"user_id": uid, "amount": Decimal("10.00"), "category": "Casa"}
    add(Transaction(type="expense", due_date=D("2026-11-05"), paid_at=paid, **expense))
    add(Transaction(type="income", due_date=D("2026-11-05"), **expense))
    add(Transaction(type="expense", due_date=D("2026-10-31"), **expense))  # overdue, but before the range
    mel = add(Pet(user_id=uid, name="Mel", species="Cachorro"))
    series = {"pet_id": mel.id, "user_id": uid, "type": "vaccine"}
    add(PetEvent(description="V10", occurred_on=D("2025-11-01"), next_due_on=D("2026-11-05"), **series))
    add(PetEvent(description="v10 ", occurred_on=D("2026-10-30"), next_due_on=D("2027-10-30"), **series))
    add(Event(user_id=uid, title="Outubro", starts_on=D("2026-10-31")))

    assert get(headers) == []


def test_other_users_data_never_shows_up(ana, bia, add, get):
    uid = bia[0].id
    add(Event(user_id=uid, title="Da Bia", starts_on=D("2026-11-10")))
    add(Task(user_id=uid, title="Da Bia", due_date=D("2026-11-10")))
    add(
        Transaction(
            user_id=uid, type="expense", amount=Decimal("1.00"), category="X", due_date=D("2026-11-10")
        )
    )
    pet = add(Pet(user_id=uid, name="Rex", species="Cachorro"))
    add(
        PetEvent(
            pet_id=pet.id, user_id=uid, type="vet", occurred_on=D("2026-10-01"), next_due_on=D("2026-11-10")
        )
    )

    assert get(ana[1]) == []
    assert len(get(bia[1])) == 4


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"from": "2026-11-30", "to": "2026-11-01"}, agenda.RANGE_REVERSED),
        ({"from": "2026-01-01", "to": "2027-01-02"}, agenda.RANGE_TOO_LONG),
    ],
)
def test_invalid_range_is_422(client, ana, params, message):
    response = client.get(URL, params=params, headers=ana[1])

    assert response.status_code == 422
    assert [error["msg"] for error in response.json()["detail"]] == [message]


def test_requires_authentication(client):
    assert client.get(URL, params=RANGE).status_code == 401


def test_reads_in_one_snapshot_like_the_dashboard(client, ana, override_settings, caplog):
    # The test session cannot take the REPEATABLE READ snapshot: strict mode proves the service asks for it.
    override_settings(dashboard_require_snapshot=True)

    response = client.get(URL, params=RANGE, headers=ana[1])

    assert response.status_code == 500
    assert [r.exc_info[0] for r in caplog.records if r.exc_info] == [SnapshotUnavailableError]
