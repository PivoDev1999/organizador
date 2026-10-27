"""Dashboard (painel): a summary of the day built only from the other modules' reads. No table of its own.

Every rule comes from the module that owns it (overdue tasks, routine schedule, pantry alerts, reminder
series, bills to pay, monthly totals, budget alerts); this service only picks "today", the window and
the list size, and runs all reads in one REPEATABLE READ, READ ONLY transaction
(`snapshot_repo.begin_read_snapshot`), so every number reflects the same instant: a bill paid by
another device while the dashboard is being built shows up either as pending in `upcoming` and in the
month's pending total, or as paid in both, never in both states.

"Today" is read once, so a request that crosses midnight still uses a single date everywhere.
"""

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import Settings
from app.core.finance import MonthSummary, month_of
from app.models import Task, TaskStatus
from app.repositories import snapshot as snapshot_repo
from app.services import budget as budget_service
from app.services import pantry as pantry_service
from app.services import pet as pet_service
from app.services import routine as routine_service
from app.services import shopping as shopping_service
from app.services import task as task_service
from app.services import transaction as transaction_service
from app.services.budget import BudgetAlert
from app.services.pantry import PantryAlertsPreview
from app.services.pet import PetReminder
from app.services.routine import DueRoutine
from app.services.shopping import ShoppingSummary
from app.services.transaction import TransactionView


@dataclass(frozen=True)
class Dashboard:
    """Each `tuple[list[X], int]` holds up to `limit` items and the total of matches."""

    date: date
    overdue_tasks: tuple[list[Task], int]
    tasks_due_today: tuple[list[Task], int]
    doing_tasks: int
    routines: list[DueRoutine]
    pantry: PantryAlertsPreview
    shopping: ShoppingSummary
    pet_reminders: tuple[list[PetReminder], int]
    upcoming_bills: tuple[list[TransactionView], int]
    month: MonthSummary
    budget_alerts: tuple[list[BudgetAlert], int]


def get_dashboard(db: Session, settings: Settings, user_id: uuid.UUID, within: int, limit: int) -> Dashboard:
    """The user's summary of today. `within` (days) is the window of pantry expiry, pet reminders and
    bills; `limit` caps each list (routines excepted: the day's score needs all of them).

    Budget alerts are cut in Python: their level is a pure rule (`budget_alert_level`) applied to the
    month's budgets, which a household counts in tens.
    """
    snapshot_repo.begin_read_snapshot(db, require=settings.dashboard_require_snapshot)
    today = clock.today(settings.timezone)
    month = month_of(today)
    alerts = budget_service.list_alerts(db, user_id, month)
    return Dashboard(
        date=today,
        overdue_tasks=task_service.list_overdue(db, user_id, today, limit),
        tasks_due_today=task_service.list_open_due_on(db, user_id, today, limit),
        doing_tasks=task_service.count_with_status(db, user_id, TaskStatus.DOING),
        routines=routine_service.list_due_on(db, user_id, today),
        pantry=pantry_service.get_alerts_preview(db, user_id, today, within, limit),
        shopping=shopping_service.get_summary(db, user_id),
        pet_reminders=pet_service.list_reminders_preview(db, user_id, today, within, limit),
        # Bills before the month totals: with the snapshot, both see the same payments.
        upcoming_bills=transaction_service.list_upcoming_preview(db, settings, user_id, today, within, limit),
        month=transaction_service.get_month_totals(db, user_id, month),
        budget_alerts=(alerts[:limit], len(alerts)),
    )
