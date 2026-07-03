import pytest

from app.exceptions import NotFoundError
from app.repositories.group_repository import InMemoryGroupRepository
from app.repositories.task_group_repository import InMemoryTaskGroupRepository
from app.repositories.task_repository import InMemoryTaskRepository
from app.repositories.user_repository import InMemoryUserRepository
from app.services.group_service import GroupService
from app.services.task_group_service import TaskGroupService
from app.services.task_service import TaskService
from app.services.user_service import UserService


@pytest.fixture
def user_service() -> UserService:
    return UserService(InMemoryUserRepository())


@pytest.fixture
def group_service(user_service: UserService) -> GroupService:
    return GroupService(InMemoryGroupRepository(), user_service)


@pytest.fixture
def task_service(user_service: UserService) -> TaskService:
    return TaskService(InMemoryTaskRepository(), user_service)


@pytest.fixture
def task_group_service(
    task_service: TaskService, group_service: GroupService, user_service: UserService
) -> TaskGroupService:
    return TaskGroupService(InMemoryTaskGroupRepository(), task_service, group_service, user_service)


def _setup(user_service, group_service, task_service):
    creator = user_service.create_user(first_name="Ada", last_name="Lovelace")
    assignee = user_service.create_user(first_name="Bob", last_name="Smith")
    group = group_service.create_group(
        group_name="Smiths", group_desc=None, group_category="Family", creater_id=creator.userId
    )
    task = task_service.create_task(task_title="Buy milk", created_by=creator.userId)
    return creator, assignee, group, task


def test_assign_raises_if_task_missing(task_group_service, user_service, group_service, task_service):
    _, assignee, group, _ = _setup(user_service, group_service, task_service)
    with pytest.raises(NotFoundError):
        task_group_service.assign("unknown-task", group.groupId, assignee.userId)


def test_assign_raises_if_group_missing(task_group_service, user_service, group_service, task_service):
    _, assignee, _, task = _setup(user_service, group_service, task_service)
    with pytest.raises(NotFoundError):
        task_group_service.assign(task.taskId, "unknown-group", assignee.userId)


def test_assign_raises_if_assignee_missing(task_group_service, user_service, group_service, task_service):
    _, _, group, task = _setup(user_service, group_service, task_service)
    with pytest.raises(NotFoundError):
        task_group_service.assign(task.taskId, group.groupId, "unknown-user")


def test_assign_creates_relationship(task_group_service, user_service, group_service, task_service):
    _, assignee, group, task = _setup(user_service, group_service, task_service)
    relationship = task_group_service.assign(task.taskId, group.groupId, assignee.userId)
    assert relationship.uuid
    assert relationship.taskId == task.taskId
    assert relationship.groupId == group.groupId
    assert relationship.assigneeId == assignee.userId


def test_assign_twice_updates_existing_relationship(
    task_group_service, user_service, group_service, task_service
):
    creator, assignee, group, task = _setup(user_service, group_service, task_service)
    first = task_group_service.assign(task.taskId, group.groupId, assignee.userId)
    second = task_group_service.assign(task.taskId, group.groupId, creator.userId)
    assert first.uuid == second.uuid
    assert second.assigneeId == creator.userId


def test_unassign_clears_assignee(task_group_service, user_service, group_service, task_service):
    _, assignee, group, task = _setup(user_service, group_service, task_service)
    task_group_service.assign(task.taskId, group.groupId, assignee.userId)
    result = task_group_service.unassign(task.taskId, group.groupId, assignee.userId)
    assert result.assigneeId is None


def test_unassign_raises_if_no_matching_assignment(
    task_group_service, user_service, group_service, task_service
):
    _, assignee, group, task = _setup(user_service, group_service, task_service)
    with pytest.raises(NotFoundError):
        task_group_service.unassign(task.taskId, group.groupId, assignee.userId)
