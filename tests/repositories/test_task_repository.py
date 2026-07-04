from datetime import datetime, timezone

from app.db.orm_models import UserRow
from app.models.enums import TaskState, UserStatus
from app.models.task import Task
from app.repositories.task_repository import TaskRepository


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


def _make_task(task_id="task-1", created_by="user-1") -> Task:
    return Task(
        taskId=task_id,
        taskTitle="Buy milk",
        createdAt=datetime.now(timezone.utc),
        createdBy=created_by,
    )


def test_add_and_get_round_trips_all_fields(db_session):
    _make_user_row(db_session)
    repo = TaskRepository(db_session)
    task = _make_task()

    repo.add(task)
    fetched = repo.get(task.taskId)

    assert fetched is not None
    assert fetched.taskTitle == "Buy milk"
    assert fetched.taskState == TaskState.TODO
    assert fetched.createdBy == "user-1"


def test_get_unknown_id_returns_none(db_session):
    repo = TaskRepository(db_session)
    assert repo.get("unknown-id") is None


def test_update_persists_changes(db_session):
    _make_user_row(db_session)
    repo = TaskRepository(db_session)
    task = _make_task()
    repo.add(task)

    updated = task.model_copy(
        update={"taskTitle": "Buy oat milk", "taskState": TaskState.IN_PROGRESS}
    )
    repo.update(updated)

    fetched = repo.get(task.taskId)
    assert fetched.taskTitle == "Buy oat milk"
    assert fetched.taskState == TaskState.IN_PROGRESS


def test_list_all_returns_every_task(db_session):
    _make_user_row(db_session)
    repo = TaskRepository(db_session)
    repo.add(_make_task("task-1"))
    repo.add(_make_task("task-2"))

    all_tasks = repo.list_all()

    assert {t.taskId for t in all_tasks} == {"task-1", "task-2"}


def test_list_by_creator_filters_correctly(db_session):
    _make_user_row(db_session, "user-1")
    _make_user_row(db_session, "user-2")
    repo = TaskRepository(db_session)
    repo.add(_make_task("task-1", "user-1"))
    repo.add(_make_task("task-2", "user-2"))

    results = repo.list_by_creator("user-1")

    assert [t.taskId for t in results] == ["task-1"]
