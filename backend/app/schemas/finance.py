import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Annotated, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from app.core.finance import MIN_DUE_DATE, MIN_PAID_ON, BudgetAlertLevel, TransactionStatus
from app.models.finance import TransactionSort, TransactionType
from app.schemas.common import (
    DbText,
    IsoDate,
    Money,
    MoneyTotal,
    NotNull,
    PageQuery,
    YearMonth,
    decimal_output_type,
    drop_blanks,
    optional_text,
    required_text,
)

if TYPE_CHECKING:  # services import this module: no runtime import back
    from app.core.finance import MonthSummary
    from app.services.budget import BudgetAlert, BudgetCopyResult, BudgetView
    from app.services.transaction import TransactionView

# Column sizes of transactions and budgets.
CATEGORY_MAX_LENGTH = 100
DESCRIPTION_MAX_LENGTH = 255
SEARCH_MAX_LENGTH = 255
UPCOMING_MAX_WITHIN = 365
UPCOMING_DEFAULT_WITHIN = 7

Category = Annotated[
    DbText,
    AfterValidator(
        required_text(
            CATEGORY_MAX_LENGTH,
            "Informe a categoria.",
            f"A categoria deve ter no máximo {CATEGORY_MAX_LENGTH} caracteres.",
        )
    ),
    NotNull,
]
# Blank (after strip) becomes None.
Description = Annotated[
    DbText,
    AfterValidator(
        optional_text(
            DESCRIPTION_MAX_LENGTH, f"A descrição deve ter no máximo {DESCRIPTION_MAX_LENGTH} caracteres."
        )
    ),
]
SearchText = Annotated[
    DbText,
    AfterValidator(
        optional_text(SEARCH_MAX_LENGTH, f"A busca deve ter no máximo {SEARCH_MAX_LENGTH} caracteres.")
    ),
]
CategoryFilter = Annotated[
    DbText,
    AfterValidator(
        optional_text(
            CATEGORY_MAX_LENGTH, f"A categoria deve ter no máximo {CATEGORY_MAX_LENGTH} caracteres."
        )
    ),
]


def _not_before(floor: date, message: str):
    def _check(value: date) -> date:
        if value < floor:
            raise ValueError(message)
        return value

    return AfterValidator(_check)


# Payment and due dates have a floor (see app.core.finance); query filters do not need one.
PaidOn = Annotated[
    IsoDate, _not_before(MIN_PAID_ON, f"A data de pagamento deve ser a partir de {MIN_PAID_ON:%d/%m/%Y}.")
]
DueDateValue = Annotated[
    IsoDate, _not_before(MIN_DUE_DATE, f"O vencimento deve ser a partir de {MIN_DUE_DATE:%d/%m/%Y}.")
]
PositiveMoney = Annotated[Money, Field(gt=0), NotNull]
NonNegativeMoney = Annotated[Money, Field(ge=0), NotNull]
Type = Annotated[TransactionType, NotNull]
DueDate = Annotated[DueDateValue, NotNull]
Percent = decimal_output_type(1, "Percentual com 1 casa, como texto.")

_AMOUNT_DESCRIPTION = 'Valor em reais, maior que 0: texto (ex.: "12.90") ou inteiro; float dá 422.'
_PET_DESCRIPTION = "Pet ligado ao gasto (ex.: ração, veterinário). Pet de outro usuário: 422."
_PAID_ON_DESCRIPTION = (
    "Dia do pagamento (no fuso do servidor); não pode ser no futuro. Hoje grava o instante atual; outro "
    "dia grava o meio-dia local daquele dia."
)

# Unknown fields are rejected (422), not ignored. Enums are stored as their plain string values.
_INPUT_CONFIG = ConfigDict(extra="forbid", use_enum_values=True)


# --- transactions ---------------------------------------------------------------------------------


class TransactionCreate(BaseModel):
    """With `paid_on` the transaction is created already paid. `paid_on` must not be in the future:
    that depends on today, so the service checks it."""

    model_config = _INPUT_CONFIG

    type: Type
    amount: PositiveMoney = Field(description=_AMOUNT_DESCRIPTION)
    category: Category
    description: Description | None = None
    due_date: DueDate = Field(description="Vencimento. Define o mês da transação (regime de competência).")
    pet_id: uuid.UUID | None = Field(default=None, description=_PET_DESCRIPTION)
    paid_on: PaidOn | None = Field(default=None, description=_PAID_ON_DESCRIPTION)


class TransactionUpdate(BaseModel):
    """Partial update: only the fields present in the body change (see `model_fields_set`).

    `type`, `amount`, `category` and `due_date` may be omitted but not sent as null (NotNull, 422);
    `description` and `pet_id` accept null to clear the value. Payment is not editable here (unknown
    field, 422): use `/pay` and `/unpay`.
    """

    model_config = _INPUT_CONFIG

    type: Type = None
    amount: PositiveMoney = Field(default=None, description=_AMOUNT_DESCRIPTION)
    category: Category = None
    description: Description | None = None
    due_date: DueDate = None
    pet_id: uuid.UUID | None = Field(default=None, description=_PET_DESCRIPTION)


class TransactionPay(BaseModel):
    model_config = _INPUT_CONFIG

    paid_on: PaidOn | None = Field(default=None, description=f"{_PAID_ON_DESCRIPTION} Padrão: hoje.")


class TransactionRead(BaseModel):
    id: uuid.UUID
    type: TransactionType
    amount: Money
    category: str
    description: str | None
    due_date: date
    pet_id: uuid.UUID | None
    paid_at: datetime | None = Field(description="Instante do pagamento (UTC); null se pendente.")
    paid_on: date | None = Field(description="Dia do pagamento no fuso do servidor; null se pendente.")
    overdue: bool = Field(description="Pendente com vencimento antes de hoje (no fuso do servidor).")
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, view: "TransactionView") -> Self:
        """Build from the service view: the ORM transaction plus the values computed with the timezone."""
        tx = view.transaction
        return cls(
            id=tx.id,
            type=tx.type,
            amount=tx.amount,
            category=tx.category,
            description=tx.description,
            due_date=tx.due_date,
            pet_id=tx.pet_id,
            paid_at=tx.paid_at,
            paid_on=view.paid_on,
            overdue=view.overdue,
            created_at=tx.created_at,
            updated_at=tx.updated_at,
        )


class TransactionQuery(PageQuery):
    """Query string of `GET /api/transactions`. Every filter is optional and they combine with AND;
    the values of a repeated parameter combine with OR."""

    model_config = ConfigDict(use_enum_values=True)

    type: list[TransactionType] = Field(default=[], description="Um ou mais tipos (repita o parâmetro).")
    category: Annotated[list[CategoryFilter], AfterValidator(drop_blanks)] = Field(
        default=[], description="Uma ou mais categorias (repita o parâmetro), sem diferenciar maiúsculas."
    )
    status: list[TransactionStatus] = Field(
        default=[],
        description=(
            "pending: não paga. paid: paga. overdue: não paga e vencida antes de hoje (no fuso do "
            "servidor). Repita o parâmetro para combinar."
        ),
    )
    month: YearMonth | None = Field(
        default=None, description="Mês do vencimento (AAAA-MM). Não combina com due_from/due_to."
    )
    due_from: IsoDate | None = Field(default=None, description="Vencimento a partir desta data (inclusiva).")
    due_to: IsoDate | None = Field(default=None, description="Vencimento até esta data (inclusiva).")
    pet_id: uuid.UUID | None = Field(default=None, description="Só as transações ligadas a este pet.")
    q: SearchText | None = Field(default=None, description="Busca na descrição, sem diferenciar maiúsculas.")
    sort: TransactionSort = Field(
        default=TransactionSort.DUE_DATE, description="Ordenação; prefixo '-' para decrescente."
    )

    @model_validator(mode="after")
    def _check_dates(self) -> Self:
        if self.month is not None and (self.due_from is not None or self.due_to is not None):
            raise ValueError("Use month ou due_from/due_to, não os dois.")
        if self.due_from is not None and self.due_to is not None and self.due_from > self.due_to:
            raise ValueError("A data inicial (due_from) não pode ser posterior à data final (due_to).")
        return self


class UpcomingQuery(BaseModel):
    within: int = Field(
        default=UPCOMING_DEFAULT_WITHIN,
        ge=0,
        le=UPCOMING_MAX_WITHIN,
        description="Janela em dias (0 a 365): vencimentos até hoje + N. Atrasadas sempre entram.",
    )


class MonthQuery(BaseModel):
    month: YearMonth | None = Field(default=None, description="Mês (AAAA-MM). Padrão: o mês atual.")


class TotalsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total: MoneyTotal
    paid: MoneyTotal
    pending: MoneyTotal


class BalanceRead(BaseModel):
    total: MoneyTotal = Field(description="Receitas menos despesas do mês, pagas ou não. Pode ser negativo.")
    paid: MoneyTotal = Field(description="Receitas pagas menos despesas pagas. Pode ser negativo.")


class CategoryTotalsRead(TotalsRead):
    type: TransactionType
    category: str = Field(description="Grafia da transação criada mais recentemente do grupo.")


def _month_fields(summary: "MonthSummary") -> dict:
    return {
        "month": summary.month,
        "income": summary.income,
        "expense": summary.expense,
        "balance": {"total": summary.balance_total, "paid": summary.balance_paid},
    }


class MonthTotalsRead(BaseModel):
    """Totals of the month (accrual basis), without the breakdown by category."""

    model_config = ConfigDict(from_attributes=True)

    month: YearMonth
    income: TotalsRead
    expense: TotalsRead
    balance: BalanceRead

    @classmethod
    def of(cls, summary: "MonthSummary") -> Self:
        """Build from the service summary (dataclasses read via attributes) plus the computed balance."""
        return cls.model_validate(_month_fields(summary), from_attributes=True)


class SummaryRead(MonthTotalsRead):
    by_category: list[CategoryTotalsRead] = Field(
        description=(
            "Totais por tipo e categoria (sem diferenciar maiúsculas): despesas primeiro, depois "
            "receitas; maior total primeiro."
        )
    )

    @classmethod
    def of(cls, summary: "MonthSummary") -> Self:
        """Build from the service summary (dataclasses read via attributes) plus the computed balance."""
        return cls.model_validate(
            {**_month_fields(summary), "by_category": summary.by_category}, from_attributes=True
        )


# --- budgets --------------------------------------------------------------------------------------


class BudgetCreate(BaseModel):
    model_config = _INPUT_CONFIG

    category: Category
    month: Annotated[YearMonth, NotNull] = Field(description="Mês do orçamento (AAAA-MM).")
    amount: NonNegativeMoney = Field(description="Limite em reais (0 ou mais): texto ou inteiro.")


class BudgetUpdate(BaseModel):
    """Only the amount changes. Category and month are the budget's identity: delete and create."""

    model_config = _INPUT_CONFIG

    amount: NonNegativeMoney = Field(default=None, description="Limite em reais (0 ou mais).")


class BudgetRead(BaseModel):
    id: uuid.UUID
    category: str
    month: YearMonth
    amount: Money
    spent: MoneyTotal = Field(
        description="Despesas do mês na categoria (sem diferenciar maiúsculas), pagas ou não."
    )
    remaining: MoneyTotal = Field(description="amount - spent. Negativo quando estourou.")
    percent_used: Percent | None = Field(
        description="spent / amount em %, 1 casa (arredonda metade para cima). null se amount = 0."
    )

    @classmethod
    def of(cls, view: "BudgetView") -> Self:
        budget = view.budget
        return cls(
            id=budget.id,
            category=budget.category,
            month=budget.month,
            amount=budget.amount,
            spent=view.spent,
            remaining=view.remaining,
            percent_used=view.percent_used,
        )


class BudgetAlertRead(BudgetRead):
    level: BudgetAlertLevel = Field(
        description=(
            "Calculado com os valores exatos, sem arredondar. warning: gasto de 80% a 100% do orçamento "
            "(inclusive). exceeded: gasto maior que o orçamento, ou qualquer gasto "
            "num orçamento de 0."
        )
    )

    @classmethod
    def of_alert(cls, alert: "BudgetAlert") -> Self:
        return cls(**BudgetRead.of(alert.view).model_dump(), level=alert.level)


class BudgetCopyQuery(BaseModel):
    source: YearMonth = Field(alias="from", description="Mês de origem (AAAA-MM).")
    target: YearMonth = Field(alias="to", description="Mês de destino (AAAA-MM).")

    @model_validator(mode="after")
    def _check_months(self) -> Self:
        if self.source == self.target:
            raise ValueError("Os meses de origem (from) e destino (to) devem ser diferentes.")
        return self


class BudgetCopyRead(BaseModel):
    created: list[BudgetRead]
    skipped: list[str] = Field(description="Categorias da origem que já tinham orçamento no destino.")

    @classmethod
    def of(cls, result: "BudgetCopyResult") -> Self:
        return cls(created=[BudgetRead.of(view) for view in result.created], skipped=result.skipped)
