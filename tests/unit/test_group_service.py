import pytest

from app.exceptions import NotFoundError
from app.models.enums import GroupStatus
from app.repositories.group_repository import GroupRepository
from app.repositories.user_repository import UserRepository
from app.services.group_service import GroupService
from app.services.user_service import UserService


@pytest.fixture
def user_service(db_session) -> UserService:
    return UserService(UserRepository(db_session))


@pytest.fixture
def group_service(db_session, user_service: UserService) -> GroupService:
    return GroupService(GroupRepository(db_session), user_service)


def test_create_group_requires_existing_creator(group_service: GroupService):
    with pytest.raises(NotFoundError):
        group_service.create_group(
            group_name="Smiths",
            group_desc="Family group",
            group_category="Family",
            creater_id="unknown-user",
        )


def test_create_group_succeeds_for_existing_creator(
    group_service: GroupService, user_service: UserService
):
    creator = user_service.create_user(first_name="Ada", last_name="Lovelace")
    group = group_service.create_group(
        group_name="Smiths",
        group_desc="Family group",
        group_category="Family",
        creater_id=creator.userId,
    )
    assert group.groupId
    assert group.groupCreaterId == creator.userId
    assert group.groupStatus == GroupStatus.ACTIVE


def test_get_groups_by_creator_filters_correctly(
    group_service: GroupService, user_service: UserService
):
    creator = user_service.create_user(first_name="Ada", last_name="Lovelace")
    other = user_service.create_user(first_name="Bob", last_name="Smith")
    group_service.create_group(
        group_name="Smiths", group_desc=None, group_category="Family", creater_id=creator.userId
    )
    group_service.create_group(
        group_name="Others", group_desc=None, group_category="Office", creater_id=other.userId
    )

    groups = group_service.get_groups_by_creator(creator.userId)
    assert len(groups) == 1
    assert groups[0].groupName == "Smiths"


def test_update_group_does_not_change_category(
    group_service: GroupService, user_service: UserService
):
    creator = user_service.create_user(first_name="Ada", last_name="Lovelace")
    group = group_service.create_group(
        group_name="Smiths", group_desc=None, group_category="Family", creater_id=creator.userId
    )
    updated = group_service.update_group(group.groupId, group_name="The Smiths")
    assert updated.groupName == "The Smiths"
    assert updated.groupCategory == "Family"


def test_set_status_updates_status(group_service: GroupService, user_service: UserService):
    creator = user_service.create_user(first_name="Ada", last_name="Lovelace")
    group = group_service.create_group(
        group_name="Smiths", group_desc=None, group_category="Family", creater_id=creator.userId
    )
    updated = group_service.set_status(group.groupId, GroupStatus.IN_ACTIVE)
    assert updated.groupStatus == GroupStatus.IN_ACTIVE
