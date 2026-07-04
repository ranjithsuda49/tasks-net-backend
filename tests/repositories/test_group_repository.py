from datetime import datetime, timezone

from app.db.orm_models import UserRow
from app.models.enums import GroupStatus, UserStatus
from app.models.group import Group
from app.repositories.group_repository import GroupRepository


def _make_user_row(db_session, user_id="user-1") -> UserRow:
    row = UserRow(
        id=user_id,
        name={"firstName": "Ada", "lastName": "Lovelace"},
        user_status=UserStatus.ACTIVE,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(row)
    db_session.flush()
    return row


def _make_group(group_id="group-1", creater_id="user-1") -> Group:
    return Group(
        groupId=group_id,
        groupName="Smiths",
        groupCategory="Family",
        groupCreaterId=creater_id,
        createdAt=datetime.now(timezone.utc),
    )


def test_add_and_get_round_trips_all_fields(db_session):
    _make_user_row(db_session)
    repo = GroupRepository(db_session)
    group = _make_group()

    repo.add(group)
    fetched = repo.get(group.groupId)

    assert fetched is not None
    assert fetched.groupName == "Smiths"
    assert fetched.groupCategory == "Family"
    assert fetched.groupStatus == GroupStatus.ACTIVE
    assert fetched.groupCreaterId == "user-1"


def test_get_unknown_id_returns_none(db_session):
    repo = GroupRepository(db_session)
    assert repo.get("unknown-id") is None


def test_update_persists_changes(db_session):
    _make_user_row(db_session)
    repo = GroupRepository(db_session)
    group = _make_group()
    repo.add(group)

    updated = group.model_copy(update={"groupName": "The Smith Family"})
    repo.update(updated)

    fetched = repo.get(group.groupId)
    assert fetched.groupName == "The Smith Family"


def test_list_by_creator_filters_correctly(db_session):
    _make_user_row(db_session, "user-1")
    _make_user_row(db_session, "user-2")
    repo = GroupRepository(db_session)
    repo.add(_make_group("group-1", "user-1"))
    repo.add(_make_group("group-2", "user-2"))

    groups = repo.list_by_creator("user-1")

    assert [g.groupId for g in groups] == ["group-1"]
