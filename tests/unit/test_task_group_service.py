import pytest

from app.exceptions import BadRequestError, ErrorCode, NotFoundError
from app.repositories.group_repository import InMemoryGroupRepository
from app.repositories.task_group_repository import InMemoryTaskGroupRepository
from app.repositories.task_repository import InMemoryTaskRepository
from app.repositories.user_group_repository import InMemoryUserGroupRepository
from app.repositories.user_repository import InMemoryUserRepository
from app.services.group_service import GroupService
from app.services.task_group_service import TaskGroupService
from app.services.task_service import TaskService
from app.services.user_group_service import UserGroupService
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
def user_group_service(user_service: UserService, group_service: GroupService) -> UserGroupService:
    return UserGroupService(InMemoryUserGroupRepository(), user_service, group_service)


@pytest.fixture
def task_group_service(
    task_service: TaskService,
    group_service: GroupService,
    user_service: UserService,
    user_group_service: UserGroupService,
) -> TaskGroupService:
    return TaskGroupService(
        InMemoryTaskGroupRepository(), task_service, group_service, user_service, user_group_service
    )


def _setup(user_service, group_service, task_service, user_group_service):
    creator = user_service.create_user(first_name="Ada", last_name="Lovelace")
    assignee = user_service.create_user(first_name="Bob", last_name="Smith")
    group = group_service.create_group(
        group_name="Smiths", group_desc=None, group_category="Family", creater_id=creator.userId
    )
    task = task_service.create_task(task_title="Buy milk", created_by=creator.userId)
    user_group_service.associate(creator.userId, group.groupId, "Creator")
    user_group_service.associate(assignee.userId, group.groupId, "Member")
    return creator, assignee, group, task


def test_assign_raises_if_task_missing(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    _, assignee, group, _ = _setup(user_service, group_service, task_service, user_group_service)
    with pytest.raises(NotFoundError):
        task_group_service.assign("unknown-task", group.groupId, assignee.userId)


def test_assign_raises_if_group_missing(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    _, assignee, _, task = _setup(user_service, group_service, task_service, user_group_service)
    with pytest.raises(NotFoundError):
        task_group_service.assign(task.taskId, "unknown-group", assignee.userId)


def test_assign_raises_if_assignee_missing(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    _, _, group, task = _setup(user_service, group_service, task_service, user_group_service)
    with pytest.raises(NotFoundError):
        task_group_service.assign(task.taskId, group.groupId, "unknown-user")


def test_assign_raises_bad_request_if_assignee_not_group_member(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    _, _, group, task = _setup(user_service, group_service, task_service, user_group_service)
    outsider = user_service.create_user(first_name="Cara", last_name="Jones")
    with pytest.raises(BadRequestError) as exc_info:
        task_group_service.assign(task.taskId, group.groupId, outsider.userId)
    assert exc_info.value.error_code == ErrorCode.ASSIGNEE_NOT_GROUP_MEMBER
    assert exc_info.value.http_code == 400


def test_assign_creates_relationship(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    _, assignee, group, task = _setup(user_service, group_service, task_service, user_group_service)
    relationship = task_group_service.assign(task.taskId, group.groupId, assignee.userId)
    assert relationship.uuid
    assert relationship.taskId == task.taskId
    assert relationship.groupId == group.groupId
    assert relationship.assigneeId == assignee.userId


def test_assign_twice_updates_existing_relationship(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    creator, assignee, group, task = _setup(user_service, group_service, task_service, user_group_service)
    first = task_group_service.assign(task.taskId, group.groupId, assignee.userId)
    second = task_group_service.assign(task.taskId, group.groupId, creator.userId)
    assert first.uuid == second.uuid
    assert second.assigneeId == creator.userId


def test_unassign_clears_assignee(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    _, assignee, group, task = _setup(user_service, group_service, task_service, user_group_service)
    task_group_service.assign(task.taskId, group.groupId, assignee.userId)
    result = task_group_service.unassign(task.taskId, group.groupId, assignee.userId)
    assert result.assigneeId is None


def test_unassign_raises_if_no_matching_assignment(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    _, assignee, group, task = _setup(user_service, group_service, task_service, user_group_service)
    with pytest.raises(NotFoundError):
        task_group_service.unassign(task.taskId, group.groupId, assignee.userId)


def test_unassign_raises_if_assignee_does_not_match_current_assignment(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    creator, assignee, group, task = _setup(user_service, group_service, task_service, user_group_service)
    task_group_service.assign(task.taskId, group.groupId, creator.userId)
    with pytest.raises(NotFoundError):
        task_group_service.unassign(task.taskId, group.groupId, assignee.userId)
