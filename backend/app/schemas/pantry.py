import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.models.pantry import PantrySort
from app.schemas.common import (
    DbText,
    IsoDate,
    NotNull,
    PageQuery,
    Quantity,
    drop_blanks,
    optional_text,
    required_text,
)

# Column sizes of pantry_items.
NAME_MAX_LENGTH = 200
CATEGORY_MAX_LENGTH = 100
UNIT_MAX_LENGTH = 20
LOCATION_MAX_LENGTH = 100
SEARCH_MAX_LENGTH = 200
EXPIRING_WITHIN_MAX = 365
ALERTS_DEFAULT_EXPIRING_WITHIN = 7


ItemName = Annotated[
    DbText,
    AfterValidator(
        required_text(
            NAME_MAX_LENGTH, "Informe o nome.", f"O nome deve ter no máximo {NAME_MAX_LENGTH} caracteres."
        )
    ),
    NotNull,
]
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
Unit = Annotated[
    DbText,
    AfterValidator(
        required_text(
            UNIT_MAX_LENGTH,
            "Informe a unidade.",
            f"A unidade deve ter no máximo {UNIT_MAX_LENGTH} caracteres.",
        )
    ),
    NotNull,
]
# Blank (after strip) becomes None.
Location = Annotated[
    DbText,
    AfterValidator(
        optional_text(LOCATION_MAX_LENGTH, f"O local deve ter no máximo {LOCATION_MAX_LENGTH} caracteres.")
    ),
]
SearchText = Annotated[
    DbText,
    AfterValidator(
        optional_text(SEARCH_MAX_LENGTH, f"A busca deve ter no máximo {SEARCH_MAX_LENGTH} caracteres.")
    ),
]
# Query filters compare with the stored (already stripped) values; a blank one means "no filter".
CategoryFilter = Annotated[
    DbText,
    AfterValidator(
        optional_text(
            CATEGORY_MAX_LENGTH, f"A categoria deve ter no máximo {CATEGORY_MAX_LENGTH} caracteres."
        )
    ),
]

StockQuantity = Annotated[Quantity, Field(ge=0), NotNull]
MinQuantity = Annotated[Quantity, Field(ge=0)]
PositiveQuantity = Annotated[Quantity, Field(gt=0)]
ExpiringWithin = Annotated[int, Field(ge=0, le=EXPIRING_WITHIN_MAX)]

# Unknown fields are rejected (422), not ignored.
_INPUT_CONFIG = ConfigDict(extra="forbid")


class PantryItemCreate(BaseModel):
    model_config = _INPUT_CONFIG

    name: ItemName
    category: Category
    unit: Unit = Field(description="Unidade de medida, como kg, L ou un.")
    quantity: StockQuantity = Field(default=Decimal(0), description="Quantidade em estoque (padrão 0).")
    min_quantity: MinQuantity | None = Field(
        default=None, description="Estoque mínimo: igual ou abaixo dele, o item fica com estoque baixo."
    )
    expires_on: IsoDate | None = None
    location: Location | None = None


class PantryItemUpdate(BaseModel):
    """Partial update: only the fields present in the body change (see `model_fields_set`).

    `name`, `category`, `unit` and `quantity` may be omitted but not sent as null (NotNull, 422).
    `min_quantity`, `expires_on` and `location` accept null to clear the value.
    """

    model_config = _INPUT_CONFIG

    name: ItemName = None
    category: Category = None
    unit: Unit = None
    quantity: StockQuantity = None
    min_quantity: MinQuantity | None = None
    expires_on: IsoDate | None = None
    location: Location | None = None


class StockChange(BaseModel):
    """Body of consume/restock."""

    model_config = _INPUT_CONFIG

    amount: PositiveQuantity


class PantryItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    category: str
    quantity: Quantity
    unit: str
    min_quantity: Quantity | None
    expires_on: date | None
    location: str | None
    low_stock: bool = Field(description="Quantidade igual ou abaixo do mínimo (só se houver mínimo).")
    expired: bool = Field(description="Validade anterior a hoje (no fuso do servidor).")
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, view: Any) -> Self:
        """Build from the service view: an ORM item (read via attributes) plus its computed flags."""
        return cls.model_validate(
            {
                **{
                    field: getattr(view.item, field)
                    for field in cls.model_fields
                    if hasattr(view.item, field)
                },
                "low_stock": view.low_stock,
                "expired": view.expired,
            }
        )


class PantryAlertsRead(BaseModel):
    low_stock: list[PantryItemRead] = Field(description="Estoque baixo, por nome.")
    expired: list[PantryItemRead] = Field(description="Já vencidos, do mais antigo ao mais recente.")
    expiring_soon: list[PantryItemRead] = Field(description="Vencem de hoje até hoje + N dias, por validade.")


class PantryQuery(PageQuery):
    """Query string of `GET /api/pantry`. Every filter is optional and they combine with AND."""

    category: Annotated[list[CategoryFilter], AfterValidator(drop_blanks)] = Field(
        default=[], description="Uma ou mais categorias (repita o parâmetro); comparação exata."
    )
    location: Location | None = Field(default=None, description="Local exato, como Geladeira.")
    q: SearchText | None = Field(default=None, description="Busca no nome, sem diferenciar maiúsculas.")
    low_stock: bool = Field(
        default=False,
        description="true: só itens com estoque baixo. false: sem filtro (não é o inverso de true).",
    )
    expiring_within: ExpiringWithin | None = Field(
        default=None,
        description="Só itens que vencem até hoje + N dias (0 a 365), incluindo os já vencidos.",
    )
    expired: bool = Field(
        default=False,
        description="true: só itens vencidos (validade antes de hoje). false: sem filtro.",
    )
    sort: PantrySort = Field(
        default=PantrySort.NAME,
        description="Ordenação; prefixo '-' para decrescente. Itens sem validade ficam sempre por último.",
    )


class PantryAlertsQuery(BaseModel):
    expiring_within: ExpiringWithin = Field(
        default=ALERTS_DEFAULT_EXPIRING_WITHIN, description="Janela de 'vence em breve', em dias (0 a 365)."
    )
