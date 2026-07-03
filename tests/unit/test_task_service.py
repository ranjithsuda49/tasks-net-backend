from datetime import datetime, timedelta, timezone

import pytest

from app.exceptions import NotFoundError
from app.models.enums import TaskState
from app.repositories.task_repository import InMemoryTaskRepository
from app.repositories.user_repository import InMemoryUserRepository
from app.services.task_service import TaskService
from app.services.user_service import UserService


@pytest.fixture
def user_service() -> UserService:
    return UserService(InMemoryUserRepository())


@pytest.fixture
def task_service(user_service: UserService) -> TaskService:
    return TaskService(InMemoryTaskRepository(), user_service)


def test_create_task_requires_existing_user(task_service: TaskService):
    with pytest.raises(NotFoundError):
        task_service.create_task(task_title="Buy milk", created_by="unknown-user")


def test_create_task_defaults_to_todo(task_service: TaskService, user_service: UserService):
    user = user_service.create_user(first_name="Ada", last_name="Lovelace")
    task = task_service.create_task(task_title="Buy milk", created_by=user.userId)
    assert task.taskId
    assert task.taskState == TaskState.TODO
    assert task.createdBy == user.userId
    assert task.updatedAt is None
    assert task.updatedBy is None


def test_update_task_meta_changes_title_and_desc(task_service: TaskService, user_service: UserService):
    user = user_service.create_user(first_name="Ada", last_name="Lovelace")
    task = task_service.create_task(task_title="Buy milk", created_by=user.userId)
    updated = task_service.update_task_meta(
        task.taskId, updated_by=user.userId, task_title="Buy oat milk", task_desc="2 liters"
    )
    assert updated.taskTitle == "Buy oat milk"
    assert updated.taskDesc == "2 liters"
    assert updated.updatedBy == user.userId


def test_update_task_state_transitions(task_service: TaskService, user_service: UserService):
    user = user_service.create_user(first_name="Ada", last_name="Lovelace")
    task = task_service.create_task(task_title="Buy milk", created_by=user.userId)
    updated = task_service.update_task_state(
        task.taskId, updated_by=user.userId, new_state=TaskState.IN_PROGRESS
    )
    assert updated.taskState == TaskState.IN_PROGRESS


def test_update_due_date(task_service: TaskService, user_service: UserService):
    user = user_service.create_user(first_name="Ada", last_name="Lovelace")
    task = task_service.create_task(task_title="Buy milk", created_by=user.userId)
    new_due_date = datetime.now(timezone.utc) + timedelta(days=3)
    updated = task_service.update_due_date(task.taskId, updated_by=user.userId, due_date=new_due_date)
    assert updated.taskDueDate == new_due_date


def test_get_task_raises_not_found(task_service: TaskService):
    with pytest.raises(NotFoundError):
        task_service.get_task("unknown-task")
