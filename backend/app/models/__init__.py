"""ORM models. Import every model here so Alembic autogenerate sees the full metadata."""

from app.models.base import Base, EntityMixin
from app.models.file import File, FileEntityType
from app.models.finance import Budget, Transaction, TransactionType
from app.models.pantry import PantryItem
from app.models.pet import Pet, PetEvent, PetEventType
from app.models.routine import Routine, RoutineFrequency, RoutineLog
from app.models.shopping import ShoppingItem
from app.models.task import Task, TaskPriority, TaskStatus
from app.models.user import User

__all__ = [
    "Base",
    "Budget",
    "EntityMixin",
    "File",
    "FileEntityType",
    "PantryItem",
    "Pet",
    "PetEvent",
    "PetEventType",
    "Routine",
    "RoutineFrequency",
    "RoutineLog",
    "ShoppingItem",
    "Task",
    "TaskPriority",
    "TaskStatus",
    "Transaction",
    "TransactionType",
    "User",
]
