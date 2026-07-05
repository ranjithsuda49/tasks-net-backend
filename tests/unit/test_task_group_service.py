import pytest

from app.exceptions import BadRequestError, ErrorCode, ForbiddenError, NotFoundError
from app.repositories.group_repository import GroupRepository
from app.repositories.task_group_repository import TaskGroupRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.user_group_repository import UserGroupRepository
from app.repositories.user_repository import UserRepository
from app.services.group_service import GroupService
from app.services.task_group_service import TaskGroupService
from app.services.task_service import TaskService
from app.services.user_group_service import UserGroupService
from app.services.user_service import UserService


@pytest.fixture
def user_service(db_session) -> UserService:
    return UserService(UserRepository(db_session))


@pytest.fixture
def group_service(db_session, user_service: UserService) -> GroupService:
    return GroupService(GroupRepository(db_session), user_service, UserGroupRepository(db_session))


@pytest.fixture
def task_service(db_session, user_service: UserService, group_service: GroupService) -> TaskService:
    return TaskService(
        TaskRepository(db_session), user_service, TaskGroupRepository(db_session), group_service
    )


@pytest.fixture
def user_group_service(
    db_session, user_service: UserService, group_service: GroupService
) -> UserGroupService:
    return UserGroupService(UserGroupRepository(db_session), user_service, group_service)


@pytest.fixture
def task_group_service(
    db_session,
    task_service: TaskService,
    group_service: GroupService,
    user_service: UserService,
    user_group_service: UserGroupService,
) -> TaskGroupService:
    return TaskGroupService(
        TaskGroupRepository(db_session), task_service, group_service, user_service, user_group_service
    )


def _setup(user_service, group_service, task_service, user_group_service):
    creator = user_service.create_user(user_id="ada", first_name="Ada", last_name="Lovelace")
    assignee = user_service.create_user(user_id="bob", first_name="Bob", last_name="Smith")
    group = group_service.create_group(
        group_name="Smiths", group_desc=None, group_category="Family", creater_id=creator.userId
    )
    task = task_service.create_task(task_title="Buy milk", created_by=creator.userId)
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
    outsider = user_service.create_user(user_id="cara", first_name="Cara", last_name="Jones")
    with pytest.raises(BadRequestError) as exc_info:
        task_group_service.assign(task.taskId, group.groupId, outsider.userId)
    assert exc_info.value.error_code == ErrorCode.ASSIGNEE_NOT_GROUP_MEMBER
    assert exc_info.value.http_code == 400


def test_assign_to_creator_now_succeeds(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    creator, assignee, group, task = _setup(user_service, group_service, task_service, user_group_service)
    relationship = task_group_service.assign(task.taskId, group.groupId, creator.userId)
    assert relationship.assigneeId == creator.userId


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
    other_member = user_service.create_user(user_id="cara", first_name="Cara", last_name="Jones")
    user_group_service.associate(other_member.userId, group.groupId, "Member")
    first = task_group_service.assign(task.taskId, group.groupId, assignee.userId)
    second = task_group_service.assign(task.taskId, group.groupId, other_member.userId)
    assert first.uuid == second.uuid
    assert second.assigneeId == other_member.userId


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
    task_group_service.assign(task.taskId, group.groupId, assignee.userId)
    with pytest.raises(NotFoundError):
        task_group_service.unassign(task.taskId, group.groupId, creator.userId)


def test_assign_raises_forbidden_if_caller_is_not_task_creator(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    _, assignee, group, task = _setup(user_service, group_service, task_service, user_group_service)
    with pytest.raises(ForbiddenError):
        task_group_service.assign(task.taskId, group.groupId, assignee.userId, current_user_id="outsider")


def test_unassign_raises_forbidden_if_caller_is_not_task_creator(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    _, assignee, group, task = _setup(user_service, group_service, task_service, user_group_service)
    task_group_service.assign(task.taskId, group.groupId, assignee.userId)
    with pytest.raises(ForbiddenError):
        task_group_service.unassign(
            task.taskId, group.groupId, assignee.userId, current_user_id="outsider"
        )
