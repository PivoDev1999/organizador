import datetime
from typing import TYPE_CHECKING, Any, Self

from pydantic import BaseModel, Field

from app.schemas.common import MoneyTotal
from app.schemas.finance import BudgetAlertRead, MonthTotalsRead, TransactionRead
from app.schemas.pantry import PantryItemRead
from app.schemas.pet import PetReminderRead
from app.schemas.routine import RoutineTodayRead
from app.schemas.task import TaskRead

if TYPE_CHECKING:  # services import schemas: no runtime import back
    from app.services.dashboard import Dashboard

WITHIN_MAX = 365
WITHIN_DEFAULT = 7
LIMIT_MAX = 20
LIMIT_DEFAULT = 5


class DashboardQuery(BaseModel):
    within: int = Field(
        default=WITHIN_DEFAULT,
        ge=0,
        le=WITHIN_MAX,
        description=(
            "Janela em dias (0 a 365) de 'vence em breve' na despensa, lembretes dos pets e contas a "
            "pagar: até hoje + N. Atrasados sempre entram."
        ),
    )
    limit: int = Field(
        default=LIMIT_DEFAULT,
        ge=1,
        le=LIMIT_MAX,
        description="Máximo de itens em cada lista (1 a 20); `total` conta todos. Não vale para rotinas.",
    )


class Preview[T](BaseModel):
    """The first items of a list (up to `limit`) and how many there are in all."""

    items: list[T]
    total: int = Field(description="Quantidade total, inclusive os que ficaram de fora de `items`.")

    @classmethod
    def of(cls, pair: tuple[list[Any], int], build: Any) -> Self:
        items, total = pair
        return cls(items=[build(item) for item in items], total=total)


class TasksPanelRead(BaseModel):
    overdue: Preview[TaskRead] = Field(description="Prazo antes de hoje e não concluídas, por prazo e id.")
    due_today: Preview[TaskRead] = Field(description="Prazo hoje e não concluídas.")
    doing_total: int = Field(description="Tarefas em andamento (status doing).")


class RoutinesPanelRead(BaseModel):
    due_today: list[RoutineTodayRead] = Field(
        description="Todas as rotinas previstas para hoje (sem limite), como em /routines/today."
    )
    done: int = Field(description="Quantas delas já foram feitas hoje.")
    total: int


class PantryPanelRead(BaseModel):
    """Same rules and order as /pantry/alerts (with `expiring_within` = `within`)."""

    low_stock: Preview[PantryItemRead]
    expired: Preview[PantryItemRead]
    expiring_soon: Preview[PantryItemRead]


class ShoppingPanelRead(BaseModel):
    pending: int = Field(description="Itens pendentes na lista, como em /shopping/summary.")
    estimated_total: MoneyTotal = Field(
        description="Total estimado dos pendentes, como em /shopping/summary."
    )


class PetsPanelRead(BaseModel):
    reminders: Preview[PetReminderRead] = Field(
        description="Lembretes até hoje + `within` (atrasados incluídos), como em /pets/reminders."
    )


class FinancePanelRead(BaseModel):
    upcoming: Preview[TransactionRead] = Field(
        description=(
            "Contas a pagar até hoje + `within` (atrasadas incluídas), como em /transactions/upcoming."
        ),
    )
    month: MonthTotalsRead = Field(description="Totais do mês atual, como em /transactions/summary.")
    budget_alerts: Preview[BudgetAlertRead] = Field(
        description=(
            "Orçamentos do mês atual com gasto a partir de 80% (valores exatos): estourados primeiro, "
            "depois o maior uso (gasto / orçamento, sem arredondar), depois a categoria."
        )
    )


class DashboardRead(BaseModel):
    date: datetime.date = Field(description="Hoje, no fuso do servidor.")
    tasks: TasksPanelRead
    routines: RoutinesPanelRead
    pantry: PantryPanelRead
    shopping: ShoppingPanelRead
    pets: PetsPanelRead
    finance: FinancePanelRead

    @classmethod
    def of(cls, dashboard: "Dashboard") -> Self:
        """Build from the service result (ORM rows and service views)."""
        pantry = dashboard.pantry
        routines = dashboard.routines
        return cls(
            date=dashboard.date,
            tasks=TasksPanelRead(
                overdue=Preview[TaskRead].of(dashboard.overdue_tasks, TaskRead.model_validate),
                due_today=Preview[TaskRead].of(dashboard.tasks_due_today, TaskRead.model_validate),
                doing_total=dashboard.doing_tasks,
            ),
            routines=RoutinesPanelRead(
                due_today=[RoutineTodayRead.of(item.routine, item.done_today) for item in routines],
                done=sum(item.done_today for item in routines),
                total=len(routines),
            ),
            pantry=PantryPanelRead(
                low_stock=Preview[PantryItemRead].of(pantry.low_stock, PantryItemRead.of),
                expired=Preview[PantryItemRead].of(pantry.expired, PantryItemRead.of),
                expiring_soon=Preview[PantryItemRead].of(pantry.expiring_soon, PantryItemRead.of),
            ),
            shopping=ShoppingPanelRead(
                pending=dashboard.shopping.pending, estimated_total=dashboard.shopping.estimated_total
            ),
            pets=PetsPanelRead(
                reminders=Preview[PetReminderRead].of(dashboard.pet_reminders, PetReminderRead.of)
            ),
            finance=FinancePanelRead(
                upcoming=Preview[TransactionRead].of(dashboard.upcoming_bills, TransactionRead.of),
                month=MonthTotalsRead.of(dashboard.month),
                budget_alerts=Preview[BudgetAlertRead].of(dashboard.budget_alerts, BudgetAlertRead.of_alert),
            ),
        )
