import pytest

from app.exceptions import BadRequestError, ErrorCode, NotFoundError
from app.repositories.group_repository import GroupRepository
from app.repositories.user_group_repository import UserGroupRepository
from app.repositories.user_repository import UserRepository
from app.services.group_service import GroupService
from app.services.user_group_service import UserGroupService
from app.services.user_service import UserService


@pytest.fixture
def user_service(db_session) -> UserService:
    return UserService(UserRepository(db_session))


@pytest.fixture
def group_service(db_session, user_service: UserService) -> GroupService:
    return GroupService(GroupRepository(db_session), user_service)


@pytest.fixture
def user_group_service(
    db_session, user_service: UserService, group_service: GroupService
) -> UserGroupService:
    return UserGroupService(UserGroupRepository(db_session), user_service, group_service)


def _make_user_and_group(user_service: UserService, group_service: GroupService):
    user = user_service.create_user(first_name="Ada", last_name="Lovelace")
    group = group_service.create_group(
        group_name="Smiths", group_desc=None, group_category="Family", creater_id=user.userId
    )
    return user, group


def test_associate_raises_if_user_missing(user_group_service: UserGroupService, group_service, user_service):
    _, group = _make_user_and_group(user_service, group_service)
    with pytest.raises(NotFoundError):
        user_group_service.associate("unknown-user", group.groupId, "Father")


def test_associate_raises_if_group_missing(user_group_service: UserGroupService, user_service):
    user = user_service.create_user(first_name="Ada", last_name="Lovelace")
    with pytest.raises(NotFoundError):
        user_group_service.associate(user.userId, "unknown-group", "Father")


def test_associate_raises_bad_request_if_user_is_group_creator(
    user_group_service: UserGroupService, group_service, user_service
):
    creator, group = _make_user_and_group(user_service, group_service)
    with pytest.raises(BadRequestError) as exc_info:
        user_group_service.associate(creator.userId, group.groupId, "Father")
    assert exc_info.value.error_code == ErrorCode.GROUP_CREATOR_CANNOT_BE_MEMBER
    assert exc_info.value.http_code == 400


def test_associate_creates_relationship(user_group_service: UserGroupService, group_service, user_service):
    _, group = _make_user_and_group(user_service, group_service)
    member = user_service.create_user(first_name="Bob", last_name="Smith")
    relationship = user_group_service.associate(member.userId, group.groupId, "Father")
    assert relationship.uuid
    assert relationship.userId == member.userId
    assert relationship.groupId == group.groupId
    assert relationship.relationship == "Father"


def test_associate_raises_bad_request_if_already_associated(
    user_group_service: UserGroupService, group_service, user_service
):
    _, group = _make_user_and_group(user_service, group_service)
    member = user_service.create_user(first_name="Bob", last_name="Smith")
    user_group_service.associate(member.userId, group.groupId, "Father")
    with pytest.raises(BadRequestError) as exc_info:
        user_group_service.associate(member.userId, group.groupId, "Father")
    assert exc_info.value.error_code == ErrorCode.DUPLICATE_GROUP_MEMBERSHIP
    assert exc_info.value.http_code == 400


def test_disassociate_removes_relationship(user_group_service: UserGroupService, group_service, user_service):
    _, group = _make_user_and_group(user_service, group_service)
    member = user_service.create_user(first_name="Bob", last_name="Smith")
    user_group_service.associate(member.userId, group.groupId, "Father")
    user_group_service.disassociate(member.userId, group.groupId)
    assert user_group_service.list_by_group(group.groupId) == []


def test_list_by_group_returns_members(user_group_service: UserGroupService, group_service, user_service):
    _, group = _make_user_and_group(user_service, group_service)
    member = user_service.create_user(first_name="Bob", last_name="Smith")
    user_group_service.associate(member.userId, group.groupId, "Father")

    members = user_group_service.list_by_group(group.groupId)

    assert len(members) == 1
    assert members[0].userId == member.userId
    assert members[0].groupId == group.groupId
    assert members[0].relationship == "Father"


def test_list_by_group_raises_if_group_missing(user_group_service: UserGroupService):
    with pytest.raises(NotFoundError):
        user_group_service.list_by_group("unknown-group")


def test_disassociate_raises_if_not_associated(user_group_service: UserGroupService, group_service, user_service):
    _, group = _make_user_and_group(user_service, group_service)
    user2 = user_service.create_user(first_name="Bob", last_name="Smith")
    with pytest.raises(NotFoundError):
        user_group_service.disassociate(user2.userId, group.groupId)
