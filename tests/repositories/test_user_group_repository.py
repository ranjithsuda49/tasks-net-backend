import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.orm_models import GroupRow, UserRow
from app.models.enums import GroupStatus, UserStatus
from app.models.user_group import UserGroupRelationship
from app.repositories.user_group_repository import UserGroupRepository


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


def _make_group_row(db_session, group_id="group-1", creater_id="user-1") -> GroupRow:
    row = GroupRow(
        id=group_id,
        group_name="Smiths",
        group_category="Family",
        group_status=GroupStatus.ACTIVE,
        group_creater_id=creater_id,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(row)
    db_session.flush()
    return row


def _make_relationship(user_id="user-1", group_id="group-1") -> UserGroupRelationship:
    return UserGroupRelationship(
        uuid=str(uuid.uuid4()), groupId=group_id, userId=user_id, relationship="Father"
    )


def test_add_and_get_round_trips_all_fields(db_session):
    _make_user_row(db_session)
    _make_group_row(db_session)
    repo = UserGroupRepository(db_session)
    relationship = _make_relationship()

    repo.add(relationship)
    fetched = repo.get(relationship.uuid)

    assert fetched is not None
    assert fetched.userId == "user-1"
    assert fetched.groupId == "group-1"
    assert fetched.relationship == "Father"


def test_find_by_user_and_group_returns_match(db_session):
    _make_user_row(db_session)
    _make_group_row(db_session)
    repo = UserGroupRepository(db_session)
    repo.add(_make_relationship())

    found = repo.find_by_user_and_group("user-1", "group-1")

    assert found is not None
    assert found.relationship == "Father"


def test_find_by_user_and_group_returns_none_when_missing(db_session):
    repo = UserGroupRepository(db_session)
    assert repo.find_by_user_and_group("unknown-user", "unknown-group") is None


def test_list_by_group_returns_members(db_session):
    _make_user_row(db_session)
    _make_group_row(db_session)
    repo = UserGroupRepository(db_session)
    repo.add(_make_relationship())

    members = repo.list_by_group("group-1")

    assert len(members) == 1
    assert members[0].userId == "user-1"


def test_delete_removes_row(db_session):
    _make_user_row(db_session)
    _make_group_row(db_session)
    repo = UserGroupRepository(db_session)
    relationship = _make_relationship()
    repo.add(relationship)

    repo.delete(relationship.uuid)

    assert repo.get(relationship.uuid) is None


def test_duplicate_user_group_pair_raises_integrity_error(db_session):
    _make_user_row(db_session)
    _make_group_row(db_session)
    repo = UserGroupRepository(db_session)
    repo.add(_make_relationship())

    with pytest.raises(IntegrityError):
        repo.add(_make_relationship())
