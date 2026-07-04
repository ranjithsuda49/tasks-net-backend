from datetime import datetime, timezone

from app.models.enums import UserStatus
from app.models.user import Name, User
from app.repositories.user_repository import UserRepository


def _make_user(user_id="user-1") -> User:
    return User(
        userId=user_id,
        name=Name(firstName="Ada", lastName="Lovelace"),
        phoneNum="555-1234",
        emailId="ada@example.com",
        userStatus=UserStatus.ACTIVE,
        createdAt=datetime.now(timezone.utc),
        updatedAt=None,
    )


def test_add_and_get_round_trips_all_fields(db_session):
    repo = UserRepository(db_session)
    user = _make_user()

    repo.add(user)
    fetched = repo.get(user.userId)

    assert fetched is not None
    assert fetched.userId == user.userId
    assert fetched.name.firstName == "Ada"
    assert fetched.name.lastName == "Lovelace"
    assert fetched.phoneNum == "555-1234"
    assert fetched.emailId == "ada@example.com"
    assert fetched.userStatus == UserStatus.ACTIVE


def test_get_unknown_id_returns_none(db_session):
    repo = UserRepository(db_session)
    assert repo.get("unknown-id") is None


def test_update_persists_changes(db_session):
    repo = UserRepository(db_session)
    user = _make_user()
    repo.add(user)

    updated = user.model_copy(update={"emailId": "ada2@example.com"})
    repo.update(updated)

    fetched = repo.get(user.userId)
    assert fetched.emailId == "ada2@example.com"


def test_list_all_returns_every_user(db_session):
    repo = UserRepository(db_session)
    repo.add(_make_user("user-1"))
    repo.add(_make_user("user-2"))

    all_users = repo.list_all()

    assert {u.userId for u in all_users} == {"user-1", "user-2"}
