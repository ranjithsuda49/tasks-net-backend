import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.orm_models import GroupRow, GroupTaskRow, TaskRow, UserRow
from app.models.enums import GroupStatus, TaskState, UserStatus
from app.models.task_group import TaskGroupRelationship
from app.repositories.task_group_repository import TaskGroupRepository


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


def _make_task_row(db_session, task_id="task-1", created_by="user-1") -> TaskRow:
    row = TaskRow(
        id=task_id,
        task_title="Buy milk",
        task_state=TaskState.TODO,
        created_at=datetime.now(timezone.utc),
        created_by=created_by,
    )
    db_session.add(row)
    db_session.flush()
    return row


def _make_relationship(
    task_id="task-1", group_id="group-1", assignee_id="user-1"
) -> TaskGroupRelationship:
    return TaskGroupRelationship(
        uuid=str(uuid.uuid4()), taskId=task_id, groupId=group_id, assigneeId=assignee_id
    )


def _seed(db_session):
    _make_user_row(db_session)
    _make_group_row(db_session)
    _make_task_row(db_session)


def test_add_and_get_round_trips_all_fields(db_session):
    _seed(db_session)
    repo = TaskGroupRepository(db_session)
    relationship = _make_relationship()

    repo.add(relationship)
    fetched = repo.get(relationship.uuid)

    assert fetched is not None
    assert fetched.taskId == "task-1"
    assert fetched.groupId == "group-1"
    assert fetched.assigneeId == "user-1"


def test_find_by_task_and_group_returns_match(db_session):
    _seed(db_session)
    repo = TaskGroupRepository(db_session)
    repo.add(_make_relationship())

    found = repo.find_by_task_and_group("task-1", "group-1")

    assert found is not None
    assert found.assigneeId == "user-1"


def test_find_by_task_and_group_returns_none_when_missing(db_session):
    repo = TaskGroupRepository(db_session)
    assert repo.find_by_task_and_group("unknown-task", "unknown-group") is None


def test_update_to_clear_assignee_updates_row_not_deletes_it(db_session):
    _seed(db_session)
    repo = TaskGroupRepository(db_session)
    relationship = _make_relationship()
    repo.add(relationship)

    cleared = relationship.model_copy(update={"assigneeId": None})
    repo.update(cleared)

    row = db_session.get(GroupTaskRow, relationship.uuid)
    assert row is not None
    assert row.assignee_id is None


def test_duplicate_task_group_pair_raises_integrity_error(db_session):
    _seed(db_session)
    repo = TaskGroupRepository(db_session)
    repo.add(_make_relationship())

    with pytest.raises(IntegrityError):
        repo.add(_make_relationship())
