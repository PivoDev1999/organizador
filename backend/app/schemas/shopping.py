import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.models.shopping import ShoppingSort
from app.schemas.common import (
    DbText,
    Money,
    MoneyTotal,
    NotNull,
    PageQuery,
    Quantity,
    drop_blanks,
    optional_text,
    required_text,
)

if TYPE_CHECKING:  # services import this module: no runtime import back
    from app.services.shopping import PurchaseResult

# Column sizes of shopping_items.
NAME_MAX_LENGTH = 200
CATEGORY_MAX_LENGTH = 100
UNIT_MAX_LENGTH = 20
SEARCH_MAX_LENGTH = 200

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
# Optional: blank (after strip) becomes None.
Unit = Annotated[
    DbText,
    AfterValidator(
        optional_text(UNIT_MAX_LENGTH, f"A unidade deve ter no máximo {UNIT_MAX_LENGTH} caracteres.")
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
ItemQuantity = Annotated[Quantity, Field(gt=0)]
UnitPrice = Annotated[Money, Field(ge=0)]

_QUANTITY_DESCRIPTION = "Quantidade a comprar (maior que 0). Sem ela, o item conta como 1 unidade no total."
_PRICE_DESCRIPTION = 'Preço estimado por unidade, em reais: texto (ex.: "12.90") ou inteiro; float dá 422.'
_PANTRY_ITEM_DESCRIPTION = (
    "Item da despensa ligado. Ao comprar, a despensa é reposta se houver quantidade e a mesma unidade."
)

# Unknown fields are rejected (422), not ignored.
_INPUT_CONFIG = ConfigDict(extra="forbid")


class ShoppingItemCreate(BaseModel):
    model_config = _INPUT_CONFIG

    name: ItemName
    category: Category
    quantity: ItemQuantity | None = Field(default=None, description=_QUANTITY_DESCRIPTION)
    unit: Unit | None = Field(default=None, description="Unidade, como kg, L ou un.")
    estimated_price: UnitPrice | None = Field(default=None, description=_PRICE_DESCRIPTION)
    pantry_item_id: uuid.UUID | None = Field(default=None, description=_PANTRY_ITEM_DESCRIPTION)


class ShoppingItemUpdate(BaseModel):
    """Partial update: only the fields present in the body change (see `model_fields_set`).

    `name` and `category` may be omitted but not sent as null (NotNull, 422); the other fields accept
    null to clear the value. `is_purchased`/`purchased_at` are not editable here (unknown field, 422):
    use the purchase and unpurchase endpoints.
    """

    model_config = _INPUT_CONFIG

    name: ItemName = None
    category: Category = None
    quantity: ItemQuantity | None = Field(default=None, description=_QUANTITY_DESCRIPTION)
    unit: Unit | None = None
    estimated_price: UnitPrice | None = Field(default=None, description=_PRICE_DESCRIPTION)
    pantry_item_id: uuid.UUID | None = Field(default=None, description=_PANTRY_ITEM_DESCRIPTION)


class ShoppingItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    category: str
    quantity: Quantity | None
    unit: str | None
    estimated_price: Money | None = Field(description="Preço estimado por unidade.")
    is_purchased: bool
    purchased_at: datetime | None
    pantry_item_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ShoppingPurchaseRead(ShoppingItemRead):
    pantry_restocked: bool = Field(description="A compra repôs o estoque do item da despensa ligado.")

    @classmethod
    def of(cls, result: "PurchaseResult") -> Self:
        """Build from the service result: the ORM item (read via attributes) plus the restock flag."""
        fields = {field: getattr(result.item, field) for field in ShoppingItemRead.model_fields}
        return cls.model_validate({**fields, "pantry_restocked": result.pantry_restocked})


class ShoppingSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pending: int = Field(description="Itens pendentes.")
    purchased: int = Field(description="Itens comprados.")
    estimated_total: MoneyTotal = Field(
        description=(
            "Soma de quantidade x preço estimado (por unidade) dos pendentes, com 2 casas (arredondamento "
            "bancário). Sem quantidade, conta 1 unidade; sem preço, não soma. Sem teto: pode passar do "
            "limite de um valor em dinheiro de entrada."
        )
    )


class ShoppingQuery(PageQuery):
    """Query string of `GET /api/shopping`. Every filter is optional and they combine with AND."""

    is_purchased: bool | None = Field(
        default=None, description="true: só comprados. false: só pendentes. Ausente: todos."
    )
    category: Annotated[list[CategoryFilter], AfterValidator(drop_blanks)] = Field(
        default=[], description="Uma ou mais categorias (repita o parâmetro); comparação exata."
    )
    q: SearchText | None = Field(default=None, description="Busca no nome, sem diferenciar maiúsculas.")
    sort: ShoppingSort = Field(
        default=ShoppingSort.CATEGORY,
        description=(
            "Ordenação; prefixo '-' para decrescente. 'category' ordena por categoria e depois nome. "
            "'-purchased_at' deixa os pendentes por último."
        ),
    )
