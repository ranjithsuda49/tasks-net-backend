from datetime import datetime, timedelta, timezone

import pytest

from app.exceptions import BadRequestError, ErrorCode, ForbiddenError, NotFoundError
from app.models.enums import TaskState
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


def test_create_task_requires_existing_user(task_service: TaskService):
    with pytest.raises(NotFoundError):
        task_service.create_task(task_title="Buy milk", created_by="unknown-user")


def test_create_task_defaults_to_todo(task_service: TaskService, user_service: UserService):
    user = user_service.create_user(user_id="ada", first_name="Ada", last_name="Lovelace")
    task = task_service.create_task(task_title="Buy milk", created_by=user.userId)
    assert task.taskId
    assert task.taskState == TaskState.TODO
    assert task.createdBy == user.userId
    assert task.updatedAt is None
    assert task.updatedBy is None


def test_update_task_meta_changes_title_and_desc(task_service: TaskService, user_service: UserService):
    user = user_service.create_user(user_id="ada", first_name="Ada", last_name="Lovelace")
    task = task_service.create_task(task_title="Buy milk", created_by=user.userId)
    assert task.updatedAt is None
    updated = task_service.update_task_meta(
        task.taskId, current_user_id=user.userId, task_title="Buy oat milk", task_desc="2 liters"
    )
    assert updated.taskTitle == "Buy oat milk"
    assert updated.taskDesc == "2 liters"
    assert updated.updatedBy == user.userId
    assert updated.updatedAt is not None


def test_update_task_state_transitions(task_service: TaskService, user_service: UserService):
    user = user_service.create_user(user_id="ada", first_name="Ada", last_name="Lovelace")
    task = task_service.create_task(task_title="Buy milk", created_by=user.userId)
    assert task.updatedAt is None
    updated = task_service.update_task_state(
        task.taskId, current_user_id=user.userId, new_state=TaskState.IN_PROGRESS
    )
    assert updated.taskState == TaskState.IN_PROGRESS
    assert updated.updatedAt is not None


def test_update_task_state_raises_bad_request_if_already_completed(
    task_service: TaskService, user_service: UserService
):
    user = user_service.create_user(user_id="ada", first_name="Ada", last_name="Lovelace")
    task = task_service.create_task(task_title="Buy milk", created_by=user.userId)
    task_service.update_task_state(task.taskId, current_user_id=user.userId, new_state=TaskState.COMPLETED)
    with pytest.raises(BadRequestError) as exc_info:
        task_service.update_task_state(task.taskId, current_user_id=user.userId, new_state=TaskState.COMPLETED)
    assert exc_info.value.error_code == ErrorCode.TASK_ALREADY_IN_REQUESTED_STATE
    assert exc_info.value.http_code == 400


def test_update_task_state_raises_bad_request_if_same_state_requested(
    task_service: TaskService, user_service: UserService
):
    user = user_service.create_user(user_id="ada", first_name="Ada", last_name="Lovelace")
    task = task_service.create_task(task_title="Buy milk", created_by=user.userId)
    with pytest.raises(BadRequestError) as exc_info:
        task_service.update_task_state(task.taskId, current_user_id=user.userId, new_state=TaskState.TODO)
    assert exc_info.value.error_code == ErrorCode.TASK_ALREADY_IN_REQUESTED_STATE
    assert exc_info.value.http_code == 400


def test_update_task_state_allows_moving_out_of_completed(
    task_service: TaskService, user_service: UserService
):
    user = user_service.create_user(user_id="ada", first_name="Ada", last_name="Lovelace")
    task = task_service.create_task(task_title="Buy milk", created_by=user.userId)
    task_service.update_task_state(task.taskId, current_user_id=user.userId, new_state=TaskState.COMPLETED)
    updated = task_service.update_task_state(
        task.taskId, current_user_id=user.userId, new_state=TaskState.TODO
    )
    assert updated.taskState == TaskState.TODO


def test_update_due_date(task_service: TaskService, user_service: UserService):
    user = user_service.create_user(user_id="ada", first_name="Ada", last_name="Lovelace")
    task = task_service.create_task(task_title="Buy milk", created_by=user.userId)
    assert task.updatedAt is None
    new_due_date = datetime.now(timezone.utc) + timedelta(days=3)
    updated = task_service.update_due_date(task.taskId, current_user_id=user.userId, due_date=new_due_date)
    assert updated.taskDueDate == new_due_date
    assert updated.updatedAt is not None


def test_update_due_date_clears_existing_due_date(task_service: TaskService, user_service: UserService):
    user = user_service.create_user(user_id="ada", first_name="Ada", last_name="Lovelace")
    task = task_service.create_task(task_title="Buy milk", created_by=user.userId)
    existing_due_date = datetime.now(timezone.utc) + timedelta(days=3)
    task_service.update_due_date(task.taskId, current_user_id=user.userId, due_date=existing_due_date)

    cleared = task_service.update_due_date(task.taskId, current_user_id=user.userId, due_date=None)

    assert cleared.taskDueDate is None
    assert cleared.updatedBy == user.userId
    assert cleared.updatedAt is not None


def test_get_task_raises_not_found(task_service: TaskService):
    with pytest.raises(NotFoundError):
        task_service.get_task("unknown-task")


def test_get_task_raises_forbidden_if_caller_is_neither_creator_nor_assignee(
    task_service: TaskService, user_service: UserService
):
    user = user_service.create_user(user_id="ada", first_name="Ada", last_name="Lovelace")
    task = task_service.create_task(task_title="Buy milk", created_by=user.userId)
    with pytest.raises(ForbiddenError):
        task_service.get_task(task.taskId, current_user_id="outsider")


def test_get_task_succeeds_for_creator(task_service: TaskService, user_service: UserService):
    user = user_service.create_user(user_id="ada", first_name="Ada", last_name="Lovelace")
    task = task_service.create_task(task_title="Buy milk", created_by=user.userId)
    fetched = task_service.get_task(task.taskId, current_user_id=user.userId)
    assert fetched.taskId == task.taskId


def test_update_task_meta_raises_forbidden_if_caller_is_not_creator(
    task_service: TaskService, user_service: UserService
):
    user = user_service.create_user(user_id="ada", first_name="Ada", last_name="Lovelace")
    task = task_service.create_task(task_title="Buy milk", created_by=user.userId)
    with pytest.raises(ForbiddenError):
        task_service.update_task_meta(
            task.taskId, current_user_id="outsider", task_title="New"
        )


def test_get_tasks_for_user_returns_created_and_assigned_sorted_by_latest(
    task_service: TaskService,
    user_service: UserService,
    group_service,
    user_group_service,
    task_group_service,
):
    creator = user_service.create_user(user_id="ada", first_name="Ada", last_name="Lovelace")
    other_owner = user_service.create_user(user_id="bob", first_name="Bob", last_name="Smith")
    task_a = task_service.create_task(task_title="Task A", created_by=creator.userId)
    task_b = task_service.create_task(task_title="Task B", created_by=other_owner.userId)
    group = group_service.create_group(
        group_name="Smiths", group_desc=None, group_category="Family", creater_id=other_owner.userId
    )
    user_group_service.associate(creator.userId, group.groupId, "Member")
    task_group_service.assign(task_b.taskId, group.groupId, creator.userId)

    results = task_service.get_tasks_for_user(creator.userId)

    result_ids = [t.taskId for t in results]
    assert set(result_ids) == {task_a.taskId, task_b.taskId}
    assert result_ids[0] == task_b.taskId


def test_create_task_with_group_id_sets_group_id_and_auto_assigns_creator(
    task_service: TaskService, user_service: UserService, group_service: GroupService, db_session
):
    creator = user_service.create_user(user_id="ada", first_name="Ada", last_name="Lovelace")
    group = group_service.create_group(
        group_name="Smiths", group_desc=None, group_category="Family", creater_id=creator.userId
    )

    task = task_service.create_task(task_title="Buy milk", created_by=creator.userId, group_id=group.groupId)

    assert task.groupId == group.groupId
    relationship = TaskGroupRepository(db_session).find_by_task_and_group(task.taskId, group.groupId)
    assert relationship is not None
    assert relationship.assigneeId == creator.userId


def test_create_task_with_group_id_as_member_succeeds(
    task_service: TaskService, user_service: UserService, group_service: GroupService, db_session
):
    creator = user_service.create_user(user_id="ada", first_name="Ada", last_name="Lovelace")
    member = user_service.create_user(user_id="bob", first_name="Bob", last_name="Smith")
    group = group_service.create_group(
        group_name="Smiths", group_desc=None, group_category="Family", creater_id=creator.userId
    )
    user_group_service = UserGroupService(UserGroupRepository(db_session), user_service, group_service)
    user_group_service.associate(member.userId, group.groupId, "Member")

    task = task_service.create_task(task_title="Buy milk", created_by=member.userId, group_id=group.groupId)

    assert task.groupId == group.groupId
    relationship = TaskGroupRepository(db_session).find_by_task_and_group(task.taskId, group.groupId)
    assert relationship.assigneeId == member.userId


def test_create_task_with_group_id_raises_forbidden_if_caller_neither_creator_nor_member(
    task_service: TaskService, user_service: UserService, group_service: GroupService
):
    creator = user_service.create_user(user_id="ada", first_name="Ada", last_name="Lovelace")
    outsider = user_service.create_user(user_id="cara", first_name="Cara", last_name="Jones")
    group = group_service.create_group(
        group_name="Smiths", group_desc=None, group_category="Family", creater_id=creator.userId
    )

    with pytest.raises(ForbiddenError):
        task_service.create_task(task_title="Buy milk", created_by=outsider.userId, group_id=group.groupId)


def test_create_task_with_unknown_group_id_raises_not_found(
    task_service: TaskService, user_service: UserService
):
    creator = user_service.create_user(user_id="ada", first_name="Ada", last_name="Lovelace")
    with pytest.raises(NotFoundError):
        task_service.create_task(task_title="Buy milk", created_by=creator.userId, group_id="unknown-group")


def test_list_tasks_by_group_filters_correctly(
    task_service: TaskService, user_service: UserService, group_service: GroupService
):
    creator = user_service.create_user(user_id="ada", first_name="Ada", last_name="Lovelace")
    group_a = group_service.create_group(
        group_name="Smiths", group_desc=None, group_category="Family", creater_id=creator.userId
    )
    group_b = group_service.create_group(
        group_name="Others", group_desc=None, group_category="Office", creater_id=creator.userId
    )
    task_service.create_task(task_title="In A", created_by=creator.userId, group_id=group_a.groupId)
    task_service.create_task(task_title="In B", created_by=creator.userId, group_id=group_b.groupId)
    task_service.create_task(task_title="No group", created_by=creator.userId)

    results = task_service.list_tasks_by_group(group_a.groupId)

    assert [t.taskTitle for t in results] == ["In A"]
