"""Demo data for local development.

Usage (from backend/): python -m scripts.seed

Idempotent: the demo user is deleted (ON DELETE CASCADE wipes all of its data) and recreated.
"""

import sys
import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import delete, func
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import Settings, get_settings
from app.core.finance import month_bounds
from app.core.security import hash_password
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

DEMO_EMAIL = "demo@organizador.local"
DEMO_NAME = "Usuário Demo"


class SeedError(RuntimeError):
    pass


def seed(session: Session, password: str | None = None, settings: Settings | None = None) -> User:
    """Recreate the demo user with sample data. Flushes but does not commit."""
    settings = settings or get_settings()
    password = password or settings.seed_user_password
    if not password or password == "change-me":
        raise SeedError(
            "SEED_USER_PASSWORD não está definida (ou ainda é 'change-me'). "
            "Defina uma senha no .env (veja o .env.example) e rode de novo."
        )

    session.execute(delete(User).where(func.lower(User.email) == DEMO_EMAIL))

    user = User(
        email=DEMO_EMAIL,
        name=DEMO_NAME,
        password_hash=hash_password(password, settings.bcrypt_rounds),
    )
    session.add(user)
    session.flush()

    today = clock.today(settings.timezone)
    now = datetime.now(UTC)
    uid = user.id

    tasks = _tasks(uid, today, now)
    routines = _routines(uid, today)
    pantry = _pantry_items(uid, today)
    shopping = _shopping_items(uid, pantry, now)
    mel, frajola = _pets(uid, today)
    session.add_all([*tasks, *routines, *pantry, *shopping, mel, frajola])
    session.add_all(_transactions(uid, today, now, mel, frajola))
    session.add_all(_budgets(uid, today))
    # No sample `files`: the seed does not touch the storage. Objects of files uploaded to the previous
    # demo user (whose rows the delete above cascaded) are left as orphans for scripts.cleanup_orphans.
    session.flush()
    return user


def _tasks(uid: uuid.UUID, today: date, now: datetime) -> list[Task]:
    return [
        Task(user_id=uid, title="Trocar a lâmpada da cozinha", priority="high", due_date=today),
        Task(
            user_id=uid,
            title="Levar o carro na revisão",
            description="Revisão dos 30 mil km. Ligar antes para agendar.",
            due_date=today + timedelta(days=7),
        ),
        Task(
            user_id=uid,
            title="Consertar a torneira do banheiro",
            status="doing",
            priority="high",
            due_date=today + timedelta(days=1),
        ),
        Task(user_id=uid, title="Organizar o armário do quarto", priority="low"),
        Task(
            user_id=uid,
            title="Renovar o seguro residencial",
            priority="high",
            due_date=today - timedelta(days=2),
        ),
        Task(
            user_id=uid,
            title="Pagar o IPTU",
            status="done",
            due_date=today - timedelta(days=5),
            completed_at=now - timedelta(days=6),
        ),
        Task(
            user_id=uid,
            title="Doar roupas que não servem mais",
            status="done",
            priority="low",
            completed_at=now - timedelta(days=1),
        ),
    ]


def _routines(uid: uuid.UUID, today: date) -> list[Routine]:
    walk = Routine(user_id=uid, name="Passear com a Mel", frequency="daily", time_of_day=time(7, 0))
    dishes = Routine(user_id=uid, name="Lavar a louça do jantar", frequency="daily", time_of_day=time(21, 0))
    plants = Routine(
        user_id=uid,
        name="Regar as plantas",
        description="Samambaia da varanda e horta de temperos.",
        frequency="weekly",
        days_of_week=[1, 4],
        time_of_day=time(8, 0),
    )
    cleaning = Routine(user_id=uid, name="Faxina geral", frequency="weekly", days_of_week=[6])
    recycling = Routine(user_id=uid, name="Separar o reciclável", frequency="weekly", days_of_week=[2, 5])
    bills = Routine(user_id=uid, name="Pagar as contas do mês", frequency="monthly", day_of_month=5)
    filter_ = Routine(
        user_id=uid,
        name="Trocar o filtro do purificador",
        frequency="monthly",
        day_of_month=15,
        is_active=False,
    )

    for days_ago in range(4):
        walk.logs.append(RoutineLog(user_id=uid, done_on=today - timedelta(days=days_ago)))
    for days_ago in (1, 2):
        dishes.logs.append(RoutineLog(user_id=uid, done_on=today - timedelta(days=days_ago)))
    cleaning.logs.append(
        RoutineLog(user_id=uid, done_on=today - timedelta(days=5), note="Faltou limpar os vidros.")
    )
    last_month = today.replace(day=1) - timedelta(days=1)
    bills.logs.append(RoutineLog(user_id=uid, done_on=last_month.replace(day=5)))

    return [walk, dishes, plants, cleaning, recycling, bills, filter_]


def _pantry_items(uid: uuid.UUID, today: date) -> list[PantryItem]:
    def item(name, category, quantity, unit, min_quantity=None, expires_in=None, location="Armário"):
        return PantryItem(
            user_id=uid,
            name=name,
            category=category,
            quantity=Decimal(quantity),
            unit=unit,
            min_quantity=Decimal(min_quantity) if min_quantity is not None else None,
            expires_on=today + timedelta(days=expires_in) if expires_in is not None else None,
            location=location,
        )

    # The first four are below the minimum and get a matching shopping item.
    return [
        item("Arroz", "Grãos", "1", "kg", "2", 180),
        item("Café", "Bebidas", "0.250", "kg", "0.5", 60),
        item("Leite integral", "Laticínios", "2", "L", "6", 4, "Geladeira"),
        item("Ração da Mel", "Pets", "1.5", "kg", "3", 90, "Área de serviço"),
        item("Feijão carioca", "Grãos", "2", "kg", "1", 200),
        item("Azeite", "Temperos", "1", "un", "1", 300),
        item("Iogurte natural", "Laticínios", "4", "un", None, 2, "Geladeira"),
        item("Detergente", "Limpeza", "3", "un", "2", None, "Área de serviço"),
    ]


def _shopping_items(uid: uuid.UUID, pantry: list[PantryItem], now: datetime) -> list[ShoppingItem]:
    rice, coffee, milk, dog_food = pantry[:4]
    # estimated_price is per unit (per kg, per L...): the list total multiplies it by the quantity.
    return [
        ShoppingItem(
            user_id=uid,
            name="Arroz",
            quantity=Decimal("5"),
            unit="kg",
            category="Grãos",
            estimated_price=Decimal("5.58"),
            pantry_item=rice,
        ),
        ShoppingItem(
            user_id=uid,
            name="Café",
            quantity=Decimal("0.5"),
            unit="kg",
            category="Bebidas",
            estimated_price=Decimal("43.00"),
            pantry_item=coffee,
        ),
        ShoppingItem(
            user_id=uid,
            name="Leite integral",
            quantity=Decimal("12"),
            unit="L",
            category="Laticínios",
            estimated_price=Decimal("4.99"),
            pantry_item=milk,
        ),
        ShoppingItem(
            user_id=uid,
            name="Ração da Mel",
            quantity=Decimal("10"),
            unit="kg",
            category="Pets",
            estimated_price=Decimal("18.99"),
            pantry_item=dog_food,
        ),
        ShoppingItem(user_id=uid, name="Pão francês", quantity=Decimal("10"), unit="un", category="Padaria"),
        ShoppingItem(user_id=uid, name="Frutas da semana", category="Hortifruti"),
        ShoppingItem(
            user_id=uid,
            name="Papel higiênico",
            quantity=Decimal("1"),
            unit="pct",
            category="Limpeza",
            estimated_price=Decimal("22.90"),
            is_purchased=True,
            purchased_at=now - timedelta(days=1),
        ),
    ]


def _pets(uid: uuid.UUID, today: date) -> tuple[Pet, Pet]:
    mel = Pet(
        user_id=uid,
        name="Mel",
        species="Cachorro",
        breed="Vira-lata caramelo",
        birth_date=date(today.year - 4, 3, 12),
        weight_kg=Decimal("14.30"),
        notes="Alérgica a frango.",
    )
    frajola = Pet(
        user_id=uid,
        name="Frajola",
        species="Gato",
        breed="SRD",
        birth_date=date(today.year - 2, 8, 1),
        weight_kg=Decimal("4.80"),
    )

    def event(type_, occurred_days_ago, next_due_in=None, description=None):
        return PetEvent(
            user_id=uid,
            type=type_,
            occurred_on=today - timedelta(days=occurred_days_ago),
            next_due_on=today + timedelta(days=next_due_in) if next_due_in is not None else None,
            description=description,
        )

    mel.events.extend(
        [
            event("vaccine", 350, 15, "Vacina V10 (reforço anual)."),
            event("vaccine", 340, 25, "Antirrábica."),
            event("medication", 80, 10, "Vermífugo."),
            event("grooming", 12, 18, "Banho e tosa higiênica."),
        ]
    )
    frajola.events.extend(
        [
            event("vet", 20, None, "Check-up anual. Tudo certo."),
            event("vaccine", 200, 165, "Vacina V4."),
            event("medication", 25, 5, "Antipulgas (pipeta)."),
        ]
    )
    return mel, frajola


def _transactions(uid: uuid.UUID, today: date, now: datetime, mel: Pet, frajola: Pet) -> list[Transaction]:
    month_start, month_end = month_bounds(today)

    def due(days: int) -> date:
        # Kept inside the current month: the summary and the budgets count by due month (accrual basis),
        # so the demo month shows every sample transaction whatever day the seed runs.
        return min(max(today + timedelta(days=days), month_start), month_end)

    def tx(description, category, amount, due_in, paid_days_ago=None, type_="expense", pet=None):
        return Transaction(
            user_id=uid,
            type=type_,
            amount=Decimal(amount),
            category=category,
            description=description,
            due_date=due(due_in),
            paid_at=now - timedelta(days=paid_days_ago) if paid_days_ago is not None else None,
            pet=pet,
        )

    salary = tx("Salário", "Salário", "6500.00", 0, None, "income")
    salary.due_date = month_start
    salary.paid_at = datetime.combine(month_start, time(9, 0), UTC)

    return [
        salary,
        tx("Conta de luz", "Moradia", "245.90", 5),
        tx("Aluguel", "Moradia", "1800.00", 10),
        tx("Internet", "Moradia", "119.90", -3, 3),
        tx("Compra do mês no mercado", "Alimentação", "862.47", -8, 8),
        tx("Ração da Mel", "Pets", "189.90", -6, 6, pet=mel),
        tx("Consulta veterinária do Frajola", "Pets", "220.00", -20, 20, pet=frajola),
        tx("Vacina V10 da Mel", "Pets", "95.00", 15, pet=mel),
        tx("Combustível", "Transporte", "250.00", -2, 2),
        tx("Farmácia", "Saúde", "74.35", -1, 1),
    ]


def _budgets(uid: uuid.UUID, today: date) -> list[Budget]:
    month = today.replace(day=1)
    limits = {
        "Moradia": "2300.00",
        "Alimentação": "1200.00",
        "Pets": "450.00",
        "Transporte": "400.00",
        "Saúde": "200.00",
        "Lazer": "300.00",
    }
    return [Budget(user_id=uid, category=c, month=month, amount=Decimal(a)) for c, a in limits.items()]


def main() -> None:
    from app.core.database import SessionLocal

    try:
        with SessionLocal() as session, session.begin():
            user = seed(session)
            email = user.email
    except SeedError as exc:
        sys.exit(f"Erro: {exc}")
    print(f"Dados de exemplo criados para {email}.")


if __name__ == "__main__":
    main()
