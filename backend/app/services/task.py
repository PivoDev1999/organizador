import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import Settings
from app.core.errors import NotFoundError
from app.core.storage import Storage
from app.models import Task, TaskSort, TaskStatus
from app.models.file import FileEntityType
from app.repositories import task as task_repo
from app.repositories.task import TaskFilters
from app.schemas.task import TaskCreate, TaskQuery, TaskUpdate
from app.services import files as files_service


class TaskNotFound(NotFoundError):
    detail = "Tarefa não encontrada."


def list_tasks(
    db: Session, settings: Settings, user_id: uuid.UUID, query: TaskQuery
) -> tuple[list[Task], int]:
    filters = TaskFilters(
        statuses=query.status,
        priorities=query.priority,
        due_from=query.due_from,
        due_to=query.due_to,
        # overdue=false means "no overdue filter", not "only tasks that are not overdue".
        overdue_before=clock.today(settings.timezone) if query.overdue else None,
        search=query.q,
    )
    return task_repo.list_for_user(db, user_id, filters, query.sort, query.limit, query.offset)


def list_overdue(db: Session, user_id: uuid.UUID, today: date, limit: int) -> tuple[list[Task], int]:
    """Up to `limit` overdue tasks (due before `today`, not done) by due date and id, plus the total.

    Same rule as `GET /api/tasks?overdue=true`.
    """
    filters = TaskFilters(overdue_before=today)
    return task_repo.list_for_user(db, user_id, filters, TaskSort.DUE_DATE, limit, 0)


def list_open_due_on(db: Session, user_id: uuid.UUID, day: date, limit: int) -> tuple[list[Task], int]:
    """Up to `limit` tasks due on `day` that are not done (by id), plus the total."""
    filters = TaskFilters(due_from=day, due_to=day, open_only=True)
    return task_repo.list_for_user(db, user_id, filters, TaskSort.DUE_DATE, limit, 0)


def count_with_status(db: Session, user_id: uuid.UUID, status: TaskStatus) -> int:
    return task_repo.count_for_user(db, user_id, TaskFilters(statuses=[status.value]))


def get_task(db: Session, user_id: uuid.UUID, task_id: uuid.UUID, *, for_update: bool = False) -> Task:
    """The user's task. Someone else's task is reported as missing (404), never as forbidden.

    Writers pass `for_update=True`: the row stays locked until their commit, so concurrent PATCH or
    DELETE requests run one after the other, each on the latest committed version.
    """
    task = task_repo.get_for_user(db, user_id, task_id, for_update=for_update)
    if task is None:
        raise TaskNotFound
    return task


def create_task(db: Session, user_id: uuid.UUID, data: TaskCreate) -> Task:
    task = Task(user_id=user_id, **data.model_dump())
    task.completed_at = clock.now_utc() if task.status == TaskStatus.DONE else None
    task_repo.add(db, task)
    db.commit()
    return task


def update_task(db: Session, user_id: uuid.UUID, task_id: uuid.UUID, data: TaskUpdate) -> Task:
    task = get_task(db, user_id, task_id, for_update=True)
    changes = {
        field: value
        for field, value in data.model_dump(exclude_unset=True).items()
        if getattr(task, field) != value
    }
    if not changes:
        # Nothing to write: commit just ends the transaction (no UPDATE, updated_at untouched) and
        # releases the row lock now, not after the response has been sent.
        db.commit()
        return task

    if "status" in changes:
        # Only real transitions reach here: done -> done keeps the original completed_at.
        task.completed_at = clock.now_utc() if changes["status"] == TaskStatus.DONE else None
    for field, value in changes.items():
        setattr(task, field, value)
    task_repo.save(db)
    db.commit()
    return task


def delete_task(db: Session, storage: Storage, user_id: uuid.UUID, task_id: uuid.UUID) -> None:
    task = get_task(db, user_id, task_id, for_update=True)
    task_repo.delete(db, task)
    keys = files_service.delete_attachments(db, user_id, FileEntityType.TASK, [task_id])
    db.commit()
    files_service.purge_objects(storage, keys)
