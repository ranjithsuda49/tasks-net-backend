import pytest

from app.exceptions import ForbiddenError, NotFoundError
from app.models.enums import UserStatus
from app.repositories.user_repository import UserRepository
from app.services.user_service import UserService


@pytest.fixture
def service(db_session) -> UserService:
    return UserService(UserRepository(db_session))


def test_create_user_generates_id_and_defaults_to_active(service: UserService):
    user = service.create_user(first_name="Ada", last_name="Lovelace")
    assert user.userId
    assert user.name.firstName == "Ada"
    assert user.name.lastName == "Lovelace"
    assert user.userStatus == UserStatus.ACTIVE
    assert user.createdAt is not None
    assert user.updatedAt is None


def test_get_user_returns_created_user(service: UserService):
    created = service.create_user(first_name="Ada", last_name="Lovelace")
    fetched = service.get_user(created.userId)
    assert fetched == created


def test_get_user_raises_not_found_for_unknown_id(service: UserService):
    with pytest.raises(NotFoundError):
        service.get_user("does-not-exist")


def test_update_user_changes_only_provided_fields(service: UserService):
    created = service.create_user(first_name="Ada", last_name="Lovelace", phone_num="123")
    updated = service.update_user(created.userId, last_name="King", email_id="ada@example.com")
    assert updated.name.firstName == "Ada"
    assert updated.name.lastName == "King"
    assert updated.phoneNum == "123"
    assert updated.emailId == "ada@example.com"
    assert created.updatedAt is None
    assert updated.updatedAt is not None


def test_set_status_updates_status(service: UserService):
    created = service.create_user(first_name="Ada", last_name="Lovelace")
    updated = service.set_status(created.userId, UserStatus.IN_ACTIVE)
    assert updated.userStatus == UserStatus.IN_ACTIVE


def test_get_user_raises_forbidden_if_caller_is_not_the_user(service: UserService):
    created = service.create_user(first_name="Ada", last_name="Lovelace")
    with pytest.raises(ForbiddenError):
        service.get_user(created.userId, current_user_id="someone-else")


def test_get_user_succeeds_if_caller_is_the_user(service: UserService):
    created = service.create_user(first_name="Ada", last_name="Lovelace")
    fetched = service.get_user(created.userId, current_user_id=created.userId)
    assert fetched.userId == created.userId


def test_update_user_raises_forbidden_if_caller_is_not_the_user(service: UserService):
    created = service.create_user(first_name="Ada", last_name="Lovelace")
    with pytest.raises(ForbiddenError):
        service.update_user(created.userId, last_name="King", current_user_id="someone-else")


def test_set_status_raises_forbidden_if_caller_is_not_the_user(service: UserService):
    created = service.create_user(first_name="Ada", last_name="Lovelace")
    with pytest.raises(ForbiddenError):
        service.set_status(created.userId, UserStatus.IN_ACTIVE, current_user_id="someone-else")
