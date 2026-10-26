import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, SettingsDep, StorageDep
from app.core.database import DbSession
from app.schemas.common import Page
from app.schemas.task import TaskCreate, TaskQuery, TaskRead, TaskUpdate
from app.services import task as task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("")
def list_tasks(
    query: Annotated[TaskQuery, Query()], db: DbSession, settings: SettingsDep, current_user: CurrentUser
) -> Page[TaskRead]:
    return Page[TaskRead].of(*task_service.list_tasks(db, settings, current_user.id, query), query)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_task(data: TaskCreate, db: DbSession, current_user: CurrentUser) -> TaskRead:
    return TaskRead.model_validate(task_service.create_task(db, current_user.id, data))


@router.get("/{task_id}")
def get_task(task_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> TaskRead:
    return TaskRead.model_validate(task_service.get_task(db, current_user.id, task_id))


@router.patch("/{task_id}")
def update_task(task_id: uuid.UUID, data: TaskUpdate, db: DbSession, current_user: CurrentUser) -> TaskRead:
    return TaskRead.model_validate(task_service.update_task(db, current_user.id, task_id, data))


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: uuid.UUID, db: DbSession, storage: StorageDep, current_user: CurrentUser) -> None:
    task_service.delete_task(db, storage, current_user.id, task_id)
