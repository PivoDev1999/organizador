"""GET /api/dashboard: the summary of the day, built from the other modules' reads.

The consistency of the snapshot (REPEATABLE READ) needs real transactions: see
tests/test_dashboard_concurrency.py.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import event

from app.core import clock
from app.core.finance import BudgetAlertLevel, budget_alert_level
from app.models import Budget, PantryItem, Pet, PetEvent, Routine, RoutineLog, ShoppingItem, Task, Transaction
from app.repositories.snapshot import SnapshotUnavailableError, begin_read_snapshot

URL = "/api/dashboard"
TODAY = date(2026, 10, 21)  # a Wednesday
NOW = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)  # 12:00 in São Paulo
WEDNESDAY, MONDAY = 3, 1  # EXTRACT(DOW)
OCTOBER, NOVEMBER, SEPTEMBER = date(2026, 10, 1), date(2026, 11, 1), date(2026, 9, 1)

# Statements of one GET /api/dashboard, counted with the test session (see test_query_ceiling): tasks 5
# (overdue list+count, due today list+count, doing count) + routines 1 + pantry 4 (one count with three
# FILTERs, three lists) + shopping 1 + pets 2 + finance 4 (budgets with spent, bills list+count, month
# totals) = 17. Savepoints are not counted. In production 2 more run: the token's user lookup (here the
# user is already in the test session) and `SET TRANSACTION` (skipped inside the test savepoints), 19 in
# all. The ceiling is the exact count, no slack: any new query must update it on purpose. It does not
# depend on how many rows exist (no N+1).
QUERY_CEILING = 17

EMPTY_PREVIEW = {"items": [], "total": 0}
ZERO_TOTALS = {"total": "0.00", "paid": "0.00", "pending": "0.00"}
EMPTY_DASHBOARD = {
    "date": "2026-10-21",
    "tasks": {"overdue": EMPTY_PREVIEW, "due_today": EMPTY_PREVIEW, "doing_total": 0},
    "routines": {"due_today": [], "done": 0, "total": 0},
    "pantry": {"low_stock": EMPTY_PREVIEW, "expired": EMPTY_PREVIEW, "expiring_soon": EMPTY_PREVIEW},
    "shopping": {"pending": 0, "estimated_total": "0.00"},
    "pets": {"reminders": EMPTY_PREVIEW},
    "finance": {
        "upcoming": EMPTY_PREVIEW,
        "month": {
            "month": "2026-10",
            "income": ZERO_TOTALS,
            "expense": ZERO_TOTALS,
            "balance": {"total": "0.00", "paid": "0.00"},
        },
        "budget_alerts": EMPTY_PREVIEW,
    },
}


def day(offset: int) -> date:
    return TODAY + timedelta(days=offset)


def ids(items: list[dict]) -> list[str]:
    return [item["id"] for item in items]


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch):
    monkeypatch.setattr(clock, "now_utc", lambda: NOW)


@pytest.fixture
def ana(authenticate):
    return authenticate("ana@example.test")


@pytest.fixture
def bia(authenticate):
    return authenticate("bia@example.test", name="Bia")


@pytest.fixture
def get(client):
    def _get(headers: dict, **params) -> dict:
        response = client.get(URL, params=params, headers=headers)
        assert response.status_code == 200, response.text
        return response.json()

    return _get


class Seed:
    """Rows of one user straight into the database (committed to the test savepoint)."""

    def __init__(self, db, user_id: uuid.UUID) -> None:
        self.db, self.user_id = db, user_id

    def _add(self, row):
        self.db.add(row)
        self.db.commit()
        return row

    def task(self, due: int | None = None, status: str = "todo", title: str = "Tarefa") -> Task:
        completed_at = NOW if status == "done" else None
        due_date = None if due is None else day(due)
        return self._add(
            Task(
                user_id=self.user_id, title=title, status=status, due_date=due_date, completed_at=completed_at
            )
        )

    def routine(self, name: str = "Rotina", done: bool = False, **fields) -> Routine:
        fields.setdefault("frequency", "daily")
        routine = self._add(Routine(user_id=self.user_id, name=name, **fields))
        if done:
            self._add(RoutineLog(routine_id=routine.id, user_id=self.user_id, done_on=TODAY))
        return routine

    def pantry(self, name: str, quantity="5", min_quantity=None, expires: int | None = None) -> PantryItem:
        return self._add(
            PantryItem(
                user_id=self.user_id,
                name=name,
                category="Mercearia",
                unit="un",
                quantity=Decimal(quantity),
                min_quantity=None if min_quantity is None else Decimal(min_quantity),
                expires_on=None if expires is None else day(expires),
            )
        )

    def shopping(self, name: str, price=None, quantity=None, purchased: bool = False) -> ShoppingItem:
        return self._add(
            ShoppingItem(
                user_id=self.user_id,
                name=name,
                category="Mercado",
                estimated_price=None if price is None else Decimal(price),
                quantity=None if quantity is None else Decimal(quantity),
                is_purchased=purchased,
                purchased_at=NOW if purchased else None,
            )
        )

    def pet(self, name: str = "Mel") -> Pet:
        return self._add(Pet(user_id=self.user_id, name=name, species="Cachorro"))

    def pet_event(
        self, pet: Pet, type_: str, occurred: int, next_due: int | None, description=None
    ) -> PetEvent:
        return self._add(
            PetEvent(
                pet_id=pet.id,
                user_id=self.user_id,
                type=type_,
                occurred_on=day(occurred),
                next_due_on=None if next_due is None else day(next_due),
                description=description,
            )
        )

    def transaction(
        self, due: int, amount="100.00", type_: str = "expense", paid: bool = False, category: str = "Casa"
    ) -> Transaction:
        return self._add(
            Transaction(
                user_id=self.user_id,
                type=type_,
                amount=Decimal(amount),
                category=category,
                due_date=day(due),
                paid_at=NOW if paid else None,
            )
        )

    def budget(self, category: str, amount, spent=None, month: date = OCTOBER) -> Budget:
        if spent is not None and Decimal(spent) > 0:
            due = (month - TODAY).days  # the 1st of that month
            self.transaction(due, amount=spent, category=category)
        return self._add(Budget(user_id=self.user_id, category=category, month=month, amount=Decimal(amount)))

    def everything(self) -> None:
        """Several rows in every section (and rows that must stay out of it)."""
        for offset, status in [(-3, "todo"), (-1, "doing"), (-1, "todo"), (-2, "done"), (0, "todo")]:
            self.task(offset, status)
        self.task(0, "doing")
        self.task(0, "done")
        self.task(5)
        self.task(None, "doing")
        self.routine("Regar plantas", done=True)
        self.routine("Lavar louça")
        self.routine("Academia", frequency="weekly", days_of_week=[WEDNESDAY])
        self.routine("Feira", frequency="weekly", days_of_week=[MONDAY])
        self.routine("Inativa", is_active=False)
        self.pantry("Arroz", quantity="1", min_quantity="2")
        self.pantry("Feijão", quantity="2", min_quantity="2", expires=-1)
        self.pantry("Óleo", quantity="0", min_quantity="1")
        self.pantry("Leite", expires=-5)
        self.pantry("Iogurte", expires=0)
        self.pantry("Queijo", expires=3)
        self.pantry("Manteiga", expires=20)
        self.pantry("Mel", expires=400)
        self.shopping("Café", price="18.90", quantity="2")
        self.shopping("Pão", price="9.99")
        self.shopping("Sal")
        self.shopping("Açúcar", price="5.00", purchased=True)
        mel, bidu = self.pet("Mel"), self.pet("Bidu")
        self.pet_event(mel, "vaccine", -380, -15, "V10")
        self.pet_event(mel, "vaccine", -10, 355, "v10 ")  # resolves the reminder above
        self.pet_event(mel, "medication", -30, -2)
        self.pet_event(bidu, "vet", -20, 3)
        self.pet_event(bidu, "grooming", -5, 25)
        self.pet_event(bidu, "other", -1, None)
        for offset in (-4, 0, 6, 30, 365, 366):
            self.transaction(offset)
        self.transaction(-1, paid=True)
        self.transaction(2, amount="5000.00", type_="income", category="Salário")
        self.transaction(-20, amount="3000.00", type_="income", paid=True, category="Salário")
        self.budget("Mercado", "100.00", "95.00")
        self.budget("Lazer", "50.00", "80.00")
        self.budget("Saúde", "100.00", "10.00")


@pytest.fixture
def seed(db_session) -> Callable[..., Seed]:
    return lambda user: Seed(db_session, user.id)


# --- access and query ----------------------------------------------------------------------------


def test_requires_authentication(client):
    response = client.get(URL)

    assert response.status_code == 401


def test_empty_dashboard_is_all_zero(ana, get):
    assert get(ana[1]) == EMPTY_DASHBOARD


@pytest.mark.parametrize(
    "params",
    [{"within": -1}, {"within": 366}, {"within": "abc"}, {"limit": 0}, {"limit": 21}],
    ids=["within-negative", "within-366", "within-text", "limit-0", "limit-21"],
)
def test_invalid_query_is_422(client, ana, params):
    response = client.get(URL, params=params, headers=ana[1])

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("within", "expected_offsets"), [(0, [-4, 0]), (365, [-4, 0, 6, 30, 365])], ids=["within-0", "within-365"]
)
def test_within_bounds_of_the_window(ana, seed, get, within, expected_offsets):
    for offset in (-4, 0, 6, 30, 365, 366):
        seed(ana[0]).transaction(offset)

    upcoming = get(ana[1], within=within, limit=20)["finance"]["upcoming"]

    assert [item["due_date"] for item in upcoming["items"]] == [day(o).isoformat() for o in expected_offsets]
    assert upcoming["total"] == len(expected_offsets)


@pytest.mark.parametrize("limit", [1, 20])
def test_limit_bounds_cap_items_but_not_totals(ana, seed, get, limit):
    data = seed(ana[0])
    tasks = [data.task(-1 - index % 3) for index in range(21)]
    for index in range(21):
        data.transaction(-index)

    body = get(ana[1], limit=limit)

    expected = sorted(tasks, key=lambda task: (task.due_date, str(task.id)))[:limit]
    assert ids(body["tasks"]["overdue"]["items"]) == [str(task.id) for task in expected]
    assert body["tasks"]["overdue"]["total"] == 21
    assert len(body["finance"]["upcoming"]["items"]) == limit
    assert body["finance"]["upcoming"]["total"] == 21


def test_defaults_are_within_7_and_limit_5(ana, seed, get):
    data = seed(ana[0])
    for offset in range(-6, 9):  # due -6 .. +8: 14 inside the default window, +8 outside
        data.transaction(offset)

    upcoming = get(ana[1])["finance"]["upcoming"]

    assert len(upcoming["items"]) == 5
    assert upcoming["total"] == 14


# --- sections ------------------------------------------------------------------------------------


def test_tasks_section(ana, seed, get):
    data = seed(ana[0])
    late = [data.task(-3), data.task(-1, "doing"), data.task(-1)]
    data.task(-2, "done")
    today = [data.task(0), data.task(0, "doing"), data.task(0)]
    data.task(0, "done")
    data.task(4)
    data.task(None, "doing")

    tasks = get(ana[1], limit=2)["tasks"]

    late_order = [late[0], *sorted(late[1:], key=lambda task: str(task.id))]
    assert ids(tasks["overdue"]["items"]) == [str(task.id) for task in late_order[:2]]
    assert tasks["overdue"]["total"] == 3
    assert ids(tasks["due_today"]["items"]) == sorted(str(task.id) for task in today)[:2]
    assert tasks["due_today"]["total"] == 3
    assert tasks["doing_total"] == 3
    assert set(tasks["overdue"]["items"][0]) == {
        "id",
        "title",
        "description",
        "status",
        "priority",
        "due_date",
        "completed_at",
        "created_at",
        "updated_at",
    }


def test_routines_section_lists_every_routine_of_today_regardless_of_limit(ana, seed, get):
    data = seed(ana[0])
    data.routine("Regar plantas", done=True)
    data.routine("Lavar louça")
    data.routine("Academia", frequency="weekly", days_of_week=[WEDNESDAY])
    data.routine("Feira", frequency="weekly", days_of_week=[MONDAY])
    data.routine("Inativa", is_active=False)

    routines = get(ana[1], limit=1)["routines"]

    assert sorted(item["name"] for item in routines["due_today"]) == [
        "Academia",
        "Lavar louça",
        "Regar plantas",
    ]
    assert [item["done_today"] for item in routines["due_today"] if item["name"] == "Regar plantas"] == [True]
    assert (routines["done"], routines["total"]) == (1, 3)


def test_pantry_section(ana, seed, get):
    data = seed(ana[0])
    data.pantry("Óleo", quantity="0", min_quantity="1")
    data.pantry("Arroz", quantity="1", min_quantity="2")
    data.pantry("Feijão", quantity="3", min_quantity="2")  # above the minimum
    data.pantry("Leite", expires=-5)
    data.pantry("Pão", expires=-1)
    data.pantry("Iogurte", expires=0)
    data.pantry("Queijo", expires=7)
    data.pantry("Manteiga", expires=8)  # outside within=7

    pantry = get(ana[1], limit=1)["pantry"]

    assert [(item["name"], item["low_stock"]) for item in pantry["low_stock"]["items"]] == [("Arroz", True)]
    assert [(item["name"], item["expired"]) for item in pantry["expired"]["items"]] == [("Leite", True)]
    assert [(item["name"], item["expired"]) for item in pantry["expiring_soon"]["items"]] == [
        ("Iogurte", False)
    ]
    totals = {name: section["total"] for name, section in pantry.items()}
    assert totals == {"low_stock": 2, "expired": 2, "expiring_soon": 2}
    assert get(ana[1], within=8)["pantry"]["expiring_soon"]["total"] == 3


def test_shopping_section(ana, seed, get):
    data = seed(ana[0])
    data.shopping("Café", price="18.90", quantity="2")
    data.shopping("Pão", price="9.99")
    data.shopping("Sal")
    data.shopping("Açúcar", price="5.00", purchased=True)

    assert get(ana[1])["shopping"] == {"pending": 3, "estimated_total": "47.79"}


def test_pets_section_keeps_the_series_rule(ana, seed, get):
    data = seed(ana[0])
    mel, bidu = data.pet("Mel"), data.pet("Bidu")
    data.pet_event(mel, "vaccine", -380, -15, "V10")
    data.pet_event(mel, "vaccine", -10, 355, "v10 ")  # newer event of the series: no reminder before it
    medication = data.pet_event(mel, "medication", -30, -2)
    data.pet_event(bidu, "vet", -20, 3)
    data.pet_event(bidu, "grooming", -5, 10)

    reminders = get(ana[1], limit=1)["pets"]["reminders"]

    assert reminders["total"] == 2
    [first] = reminders["items"]
    assert (first["event_id"], first["pet_name"], first["overdue"]) == (str(medication.id), "Mel", True)
    assert get(ana[1], within=10)["pets"]["reminders"]["total"] == 3


def test_finance_upcoming_bills(ana, seed, get):
    data = seed(ana[0])
    late, due_today = data.transaction(-3), data.transaction(0)
    data.transaction(7)
    data.transaction(8)  # outside the window
    data.transaction(-1, paid=True)
    data.transaction(1, type_="income")

    upcoming = get(ana[1], limit=2)["finance"]["upcoming"]

    assert [(item["id"], item["overdue"]) for item in upcoming["items"]] == [
        (str(late.id), True),
        (str(due_today.id), False),
    ]
    assert upcoming["total"] == 3


def test_finance_month_totals(ana, seed, get):
    data = seed(ana[0])
    data.transaction(-20, amount="5000.00", type_="income", paid=True)
    data.transaction(-5, amount="1200.00", paid=True)
    data.transaction(5, amount="300.00")
    data.transaction(-30, amount="999.00")  # September
    data.transaction(11, amount="999.00")  # November

    month = get(ana[1])["finance"]["month"]

    assert month == {
        "month": "2026-10",
        "income": {"total": "5000.00", "paid": "5000.00", "pending": "0.00"},
        "expense": {"total": "1500.00", "paid": "1200.00", "pending": "300.00"},
        "balance": {"total": "3500.00", "paid": "3800.00"},
    }


# --- budget alerts -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("spent", "amount", "level"),
    [
        ("0.00", "100.00", None),
        ("79.99", "100.00", None),
        ("7999.00", "10000.00", None),  # 79.99%
        ("7999.99", "10000.00", None),  # shown as 80.0%, still below 80% exactly
        ("80.00", "100.00", BudgetAlertLevel.WARNING),
        ("100.00", "100.00", BudgetAlertLevel.WARNING),
        ("100.01", "100.00", BudgetAlertLevel.EXCEEDED),
        ("10004.99", "10000.00", BudgetAlertLevel.EXCEEDED),  # shown as 100.0%, above 100% exactly
        ("0.00", "0.00", None),
        ("0.01", "0.00", BudgetAlertLevel.EXCEEDED),
    ],
)
def test_budget_alert_level(spent, amount, level):
    assert budget_alert_level(Decimal(spent), Decimal(amount)) == level


def test_budget_alerts_levels_and_order(ana, seed, get):
    data = seed(ana[0])
    data.budget("Mercado", "100.00", "79.90")  # no alert
    data.budget("Lazer", "100.00", "80.00")
    data.budget("Casa", "100.00", "100.00")
    data.budget("Pets", "100.00", "100.10")
    data.budget("Saúde", "0.00", "10.00")
    data.budget("Viagem", "0.00")  # no alert
    data.budget("Educação", "50.00", "100.00")
    data.budget("Bebidas", "100.00", "85.00")
    data.budget("açougue", "100.00", "85.00")  # same percent as Bebidas: pt-BR order
    data.budget("Água", "10000.00", "10004.99")  # shown as 100.0%: exceeded, after Pets (100.1%)
    data.budget("Feira", "1000.00", "850.40")  # shown as 85.0% like Bebidas, but 85.04% exactly
    data.budget("Mercado", "10.00", "50.00", month=NOVEMBER)
    data.budget("Mercado", "10.00", "50.00", month=SEPTEMBER)

    alerts = get(ana[1], limit=20)["finance"]["budget_alerts"]

    summary = [(item["category"], item["level"], item["percent_used"]) for item in alerts["items"]]
    assert summary == [
        ("Saúde", "exceeded", None),
        ("Educação", "exceeded", "200.0"),
        ("Pets", "exceeded", "100.1"),
        ("Água", "exceeded", "100.0"),
        ("Casa", "warning", "100.0"),
        ("Feira", "warning", "85.0"),
        ("açougue", "warning", "85.0"),
        ("Bebidas", "warning", "85.0"),
        ("Lazer", "warning", "80.0"),
    ]
    assert alerts["total"] == 9
    limited = get(ana[1], limit=2)["finance"]["budget_alerts"]
    assert (len(limited["items"]), limited["total"]) == (2, 9)


# --- time zone, isolation ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("now", "today", "task_section", "bill_overdue"),
    [
        (datetime(2026, 10, 22, 2, 30, tzinfo=UTC), "2026-10-21", "due_today", False),  # 23:30 in SP
        (datetime(2026, 10, 22, 3, 30, tzinfo=UTC), "2026-10-22", "overdue", True),  # 00:30 in SP
    ],
    ids=["23h30-sp", "00h30-sp"],
)
def test_today_follows_sao_paulo_across_midnight(
    ana, seed, get, monkeypatch, override_settings, now, today, task_section, bill_overdue
):
    override_settings(app_timezone="America/Sao_Paulo")
    data = seed(ana[0])
    task, bill = data.task(0), data.transaction(0)
    monkeypatch.setattr(clock, "now_utc", lambda: now)

    body = get(ana[1])

    assert body["date"] == today
    assert ids(body["tasks"][task_section]["items"]) == [str(task.id)]
    other_section = "overdue" if task_section == "due_today" else "due_today"
    assert body["tasks"][other_section]["total"] == 0
    assert [(item["id"], item["overdue"]) for item in body["finance"]["upcoming"]["items"]] == [
        (str(bill.id), bill_overdue)
    ]


def test_other_users_data_never_shows_up(ana, bia, seed, get):
    seed(bia[0]).everything()

    assert get(ana[1], within=365, limit=20) == EMPTY_DASHBOARD
    bia_view = get(bia[1], within=365, limit=20)
    assert bia_view["tasks"]["overdue"]["total"] and bia_view["finance"]["budget_alerts"]["total"]


# --- snapshot -----------------------------------------------------------------------------------


def test_snapshot_is_strict_by_default_and_lenient_only_on_request(db_session):
    # db_session runs inside savepoints of an outer transaction: the snapshot cannot be set there.
    with pytest.raises(SnapshotUnavailableError):
        begin_read_snapshot(db_session)
    assert begin_read_snapshot(db_session, require=False) is False


def test_dashboard_refuses_to_answer_without_its_snapshot(client, ana, override_settings, caplog):
    override_settings(dashboard_require_snapshot=True)

    response = client.get(URL, headers=ana[1])

    assert response.status_code == 500
    assert [r.exc_info[0] for r in caplog.records if r.exc_info] == [SnapshotUnavailableError]


# --- agreement with the source endpoints ---------------------------------------------------------


@pytest.mark.parametrize(("within", "limit"), [(0, 1), (7, 5), (30, 2), (365, 20)])
def test_each_section_agrees_with_its_source_endpoint(client, ana, seed, get, within, limit):
    seed(ana[0]).everything()
    headers = ana[1]

    def source(path: str, **params):
        response = client.get(f"/api/{path}", params=params, headers=headers)
        assert response.status_code == 200, response.text
        return response.json()

    def preview(items: list) -> dict:
        return {"items": items[:limit], "total": len(items)}

    body = get(headers, within=within, limit=limit)
    today = TODAY.isoformat()

    overdue = source("tasks", overdue="true", sort="due_date", limit=limit)
    assert body["tasks"]["overdue"] == {"items": overdue["items"], "total": overdue["total"]}
    due_today = source(
        "tasks", due_from=today, due_to=today, status=["todo", "doing"], sort="due_date", limit=limit
    )
    assert body["tasks"]["due_today"] == {"items": due_today["items"], "total": due_today["total"]}
    assert body["tasks"]["doing_total"] == source("tasks", status="doing")["total"]

    routines = source("routines/today")
    assert body["routines"] == {
        "due_today": routines,
        "done": sum(item["done_today"] for item in routines),
        "total": len(routines),
    }

    alerts = source("pantry/alerts", expiring_within=within)
    assert body["pantry"] == {name: preview(items) for name, items in alerts.items()}

    shopping = source("shopping/summary")
    assert body["shopping"] == {
        "pending": shopping["pending"],
        "estimated_total": shopping["estimated_total"],
    }

    assert body["pets"]["reminders"] == preview(source("pets/reminders", within=within))

    assert body["finance"]["upcoming"] == preview(source("transactions/upcoming", within=within))
    summary = source("transactions/summary")
    assert body["finance"]["month"] == {key: value for key, value in summary.items() if key != "by_category"}
    budgets = {budget["id"]: budget for budget in source("budgets")}
    for alert in body["finance"]["budget_alerts"]["items"]:
        assert {key: value for key, value in alert.items() if key != "level"} == budgets[alert["id"]]


# --- query ceiling -------------------------------------------------------------------------------


def test_query_ceiling(client, ana, seed, db_session):
    data = seed(ana[0])
    data.everything()
    for index in range(10):  # more rows in every list: an N+1 would add statements per row
        data.task(-1 - index)
        data.routine(f"Rotina {index}", done=index % 2 == 0)
        data.pantry(f"Item {index}", quantity="0", min_quantity="1", expires=index - 5)
        data.pet_event(data.pet(f"Pet {index}"), "vet", -1, index)
        data.transaction(index)
        data.budget(f"Categoria {index}", "10.00", "9.00")
    statements: list[str] = []

    def record(conn, cursor, statement, *args):
        if not statement.lstrip().upper().startswith(("SAVEPOINT", "RELEASE SAVEPOINT", "ROLLBACK TO")):
            statements.append(statement)

    event.listen(db_session.bind, "before_cursor_execute", record)
    try:
        response = client.get(URL, params={"within": 365, "limit": 20}, headers=ana[1])
    finally:
        event.remove(db_session.bind, "before_cursor_execute", record)

    assert response.status_code == 200
    assert response.json()["routines"]["total"] == 13
    assert len(statements) == QUERY_CEILING, "\n\n".join(statements)
