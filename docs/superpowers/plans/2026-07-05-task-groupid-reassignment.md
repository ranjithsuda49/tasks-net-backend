# Task groupId, updatedBy-from-token, and group-task reassignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement ASK.md's 6 asks: derive `updatedBy` from the auth token instead of the request body; add an optional, immutable-after-creation `groupId` to `Task`; auto-assign the creator when a task is created for a group; add `GET /api/v1/groups/{group_id}/tasks`; remove the `DELETE .../assignee/{assigneeId}` endpoint; add `PATCH .../assignee` to reassign within a group.

**Architecture:** Straight extension of the existing layered architecture (`app/api/v1` → `app/services` → `app/repositories` → `app/models`/`app/schemas`). One new Alembic migration adds a nullable `group_id` FK to `tasks`. `TaskService` gains a `GroupService` dependency (no cycle: `GroupService` never depends on `TaskService`). The pre-existing `TaskGroupRelationship` join table (`group_tasks`) is untouched in shape — it's populated automatically now, in addition to manually via `assign`/`reassign`.

**Tech Stack:** FastAPI, SQLAlchemy + psycopg3, Alembic, Pydantic, pytest against real Postgres (`tasks_net_db_test`).

## Global Constraints

- Python 3.13, existing `.venv` — no new dependencies.
- Every route already has `current_user_id: str = Depends(verify_firebase_token)` — this plan never removes that pattern, only threads the value differently.
- Full command reference: `.venv/bin/pytest -v` (full suite), `.venv/bin/pytest tests/unit/test_task_service.py -v` (single file), `.venv/bin/alembic upgrade head` (apply migrations against the dev DB — the test DB schema is created directly by `tests/conftest.py::_schema` via `Base.metadata.create_all`, so migrations only need to be applied to `tasks_net_db` for local `uvicorn` runs, but the migration file itself is still required deliverable per Ask 2).
- `ERR_TASKS_004` and (as of this plan) `ERR_TASKS_005` are intentionally-skipped gaps in the error code numbering — never reuse either number.

---

## Task 1: Exceptions — retire ERR_TASKS_005, add ERR_TASKS_007/008

**Files:**
- Modify: `app/exceptions.py`

**Interfaces:**
- Produces: `ErrorCode.REASSIGN_ASSIGNEE_UNCHANGED = "ERR_TASKS_007"`, `ErrorCode.REASSIGN_ASSIGNEE_NOT_GROUP_MEMBER = "ERR_TASKS_008"` — used by Task 7 (`TaskGroupService.reassign`).
- Removes: `ErrorCode.TASK_CREATOR_CANNOT_BE_ASSIGNEE` — no longer exists after this task; Task 6 removes its last usage.

- [ ] **Step 1: Edit `app/exceptions.py`**

Replace the `ErrorCode` class and `ERROR_CODE_MESSAGES` dict with:

```python
class ErrorCode:
    ASSIGNEE_NOT_GROUP_MEMBER = "ERR_TASKS_001"
    TASK_ALREADY_IN_REQUESTED_STATE = "ERR_TASKS_002"
    DUPLICATE_GROUP_MEMBERSHIP = "ERR_TASKS_003"
    GROUP_CREATOR_CANNOT_BE_MEMBER = "ERR_TASKS_006"
    REASSIGN_ASSIGNEE_UNCHANGED = "ERR_TASKS_007"
    REASSIGN_ASSIGNEE_NOT_GROUP_MEMBER = "ERR_TASKS_008"


ERROR_CODE_MESSAGES: dict[str, str] = {
    ErrorCode.ASSIGNEE_NOT_GROUP_MEMBER: "Assignee is not a member of the target group",
    ErrorCode.TASK_ALREADY_IN_REQUESTED_STATE: "Task is already in the requested state",
    ErrorCode.DUPLICATE_GROUP_MEMBERSHIP: "User is already associated with this group",
    ErrorCode.GROUP_CREATOR_CANNOT_BE_MEMBER: "Group creator cannot be a member of their own group",
    ErrorCode.REASSIGN_ASSIGNEE_UNCHANGED: "Requested Task assignee is same as current assignee",
    ErrorCode.REASSIGN_ASSIGNEE_NOT_GROUP_MEMBER: "Requested Assignee is not part of the Group",
}
```

(Everything else in the file — `NotFoundError`, `ForbiddenError`, `ConflictError`, `BadRequestError` — is unchanged.)

This will temporarily break two existing tests that reference `ErrorCode.TASK_CREATOR_CANNOT_BE_ASSIGNEE` — that's expected and fixed in Task 6, not here. Don't run the full suite yet.

- [ ] **Step 2: Commit**

```bash
git add app/exceptions.py
git commit -m "feat: retire ERR_TASKS_005, add ERR_TASKS_007/008 for task reassignment"
```

---

## Task 2: Alembic migration + ORM + domain model — add `groupId` to `Task`

**Files:**
- Create: `migrations/versions/<generated>_add_group_id_to_tasks.py`
- Modify: `app/db/orm_models.py`
- Modify: `app/models/task.py`

**Interfaces:**
- Produces: `TaskRow.group_id` (nullable `String(36)`, FK to `groups.id`), `Task.groupId: Optional[str] = None` — consumed by Task 3 (repository) and every later task.

- [ ] **Step 1: Generate the migration**

```bash
.venv/bin/alembic revision -m "add group_id to tasks"
```

This creates `migrations/versions/<hash>_add_group_id_to_tasks.py` with `down_revision = 'f24972e8b68b'` auto-filled (the only existing revision). Edit its `upgrade()`/`downgrade()` to:

```python
def upgrade() -> None:
    op.add_column('tasks', sa.Column('group_id', sa.String(length=36), nullable=True))
    op.create_foreign_key(None, 'tasks', 'groups', ['group_id'], ['id'])
    op.create_index(op.f('ix_tasks_group_id'), 'tasks', ['group_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_tasks_group_id'), table_name='tasks')
    op.drop_constraint('tasks_group_id_fkey', 'tasks', type_='foreignkey')
    op.drop_column('tasks', 'group_id')
```

- [ ] **Step 2: Apply it to the local dev DB**

```bash
.venv/bin/alembic upgrade head
```
Expected: no errors; `psql tasks_net_db -c '\d tasks'` shows a new `group_id` column with an FK to `groups(id)`.

(Note: `tasks_net_db_test` doesn't need this — `tests/conftest.py::_schema` calls `Base.metadata.create_all(engine)` directly from the ORM models each test session, so Step 3 below is what actually matters for the test suite.)

- [ ] **Step 3: Edit `app/db/orm_models.py`**

Add one line to `TaskRow` (after `updated_by`):

```python
class TaskRow(Base):
    __tablename__ = "tasks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_title = Column(String(200), nullable=False)
    task_desc = Column(String(2000), nullable=True)
    task_due_date = Column(DateTime(timezone=True), nullable=True)
    task_state = _enum_column(TaskState, "ck_tasks_task_state", TaskState.TODO)
    created_at = Column(DateTime(timezone=True), nullable=False)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), nullable=True)
    updated_by = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    group_id = Column(String(36), ForeignKey("groups.id"), nullable=True, index=True)
```

- [ ] **Step 4: Edit `app/models/task.py`**

```python
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.enums import TaskState


class Task(BaseModel):
    taskId: str
    taskTitle: str
    taskDesc: Optional[str] = None
    taskDueDate: Optional[datetime] = None
    taskState: TaskState = TaskState.TODO
    createdAt: datetime
    createdBy: str
    updatedAt: Optional[datetime] = None
    updatedBy: Optional[str] = None
    groupId: Optional[str] = None
```

- [ ] **Step 5: Commit**

```bash
git add migrations/versions app/db/orm_models.py app/models/task.py
git commit -m "feat: add groupId column to tasks (schema + ORM + domain model)"
```

---

## Task 3: `TaskRepository` — map `group_id`, add `list_by_group`

**Files:**
- Modify: `app/repositories/task_repository.py`
- Modify: `tests/repositories/test_task_repository.py`
- Read first: `tests/repositories/test_group_repository.py` (has `_make_group`/`_make_user_row` helpers to reuse for FK satisfaction)

**Interfaces:**
- Consumes: `Task.groupId`, `TaskRow.group_id` (Task 2).
- Produces: `TaskRepository.list_by_group(group_id: str) -> list[Task]` — consumed by Task 4 (`TaskService.list_tasks_by_group`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/repositories/test_task_repository.py` (also update the existing `_make_task` helper and add a group-row helper):

```python
from app.db.orm_models import GroupRow, UserRow
```

Replace `_make_task`:

```python
def _make_task(task_id="task-1", created_by="user-1", group_id=None) -> Task:
    return Task(
        taskId=task_id,
        taskTitle="Buy milk",
        createdAt=datetime.now(timezone.utc),
        createdBy=created_by,
        groupId=group_id,
    )
```

Add a group-row helper (mirrors `_make_user_row` in the same file):

```python
def _make_group_row(db_session, group_id="group-1", creater_id="user-1") -> GroupRow:
    row = GroupRow(
        id=group_id,
        group_name="Smiths",
        group_category="Family",
        group_creater_id=creater_id,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(row)
    db_session.flush()
    return row
```

Add new tests:

```python
def test_add_and_get_round_trips_group_id(db_session):
    _make_user_row(db_session)
    _make_group_row(db_session)
    repo = TaskRepository(db_session)
    task = _make_task(group_id="group-1")

    repo.add(task)
    fetched = repo.get(task.taskId)

    assert fetched.groupId == "group-1"


def test_list_by_group_filters_correctly(db_session):
    _make_user_row(db_session)
    _make_group_row(db_session, "group-1")
    _make_group_row(db_session, "group-2")
    repo = TaskRepository(db_session)
    repo.add(_make_task("task-1", group_id="group-1"))
    repo.add(_make_task("task-2", group_id="group-2"))

    results = repo.list_by_group("group-1")

    assert [t.taskId for t in results] == ["task-1"]


def test_update_never_changes_group_id(db_session):
    _make_user_row(db_session)
    _make_group_row(db_session, "group-1")
    _make_group_row(db_session, "group-2")
    repo = TaskRepository(db_session)
    task = _make_task(group_id="group-1")
    repo.add(task)

    attempted = task.model_copy(update={"groupId": "group-2", "taskTitle": "Buy oat milk"})
    repo.update(attempted)

    fetched = repo.get(task.taskId)
    assert fetched.taskTitle == "Buy oat milk"
    assert fetched.groupId == "group-1"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/repositories/test_task_repository.py -v
```
Expected: `test_add_and_get_round_trips_group_id` and `test_update_never_changes_group_id` FAIL with `AttributeError`/assertion mismatch (repository doesn't map `group_id` yet); `test_list_by_group_filters_correctly` FAILs with `AttributeError: 'TaskRepository' object has no attribute 'list_by_group'`.

- [ ] **Step 3: Implement — edit `app/repositories/task_repository.py`**

Full replacement content:

```python
from typing import Optional

from sqlalchemy.orm import Session

from app.db.orm_models import TaskRow
from app.models.task import Task
from app.repositories.base import BaseRepository


class TaskRepository(BaseRepository[Task]):
    def __init__(self, session: Session):
        self._session = session

    def add(self, entity: Task) -> Task:
        row = TaskRow(
            id=entity.taskId,
            task_title=entity.taskTitle,
            task_desc=entity.taskDesc,
            task_due_date=entity.taskDueDate,
            task_state=entity.taskState,
            created_at=entity.createdAt,
            created_by=entity.createdBy,
            updated_at=entity.updatedAt,
            updated_by=entity.updatedBy,
            group_id=entity.groupId,
        )
        self._session.add(row)
        self._session.flush()
        return entity

    def get(self, entity_id: str) -> Optional[Task]:
        row = self._session.get(TaskRow, entity_id)
        return self._to_domain(row) if row is not None else None

    def update(self, entity: Task) -> Task:
        # group_id is never written here: Task.groupId is immutable after
        # creation, and this is where that guarantee is enforced.
        row = self._session.get(TaskRow, entity.taskId)
        row.task_title = entity.taskTitle
        row.task_desc = entity.taskDesc
        row.task_due_date = entity.taskDueDate
        row.task_state = entity.taskState
        row.updated_at = entity.updatedAt
        row.updated_by = entity.updatedBy
        self._session.flush()
        return entity

    def list_all(self) -> list[Task]:
        return [self._to_domain(row) for row in self._session.query(TaskRow).all()]

    def list_by_creator(self, created_by: str) -> list[Task]:
        rows = self._session.query(TaskRow).filter(TaskRow.created_by == created_by).all()
        return [self._to_domain(row) for row in rows]

    def list_by_group(self, group_id: str) -> list[Task]:
        rows = self._session.query(TaskRow).filter(TaskRow.group_id == group_id).all()
        return [self._to_domain(row) for row in rows]

    @staticmethod
    def _to_domain(row: TaskRow) -> Task:
        return Task(
            taskId=row.id,
            taskTitle=row.task_title,
            taskDesc=row.task_desc,
            taskDueDate=row.task_due_date,
            taskState=row.task_state,
            createdAt=row.created_at,
            createdBy=row.created_by,
            updatedAt=row.updated_at,
            updatedBy=row.updated_by,
            groupId=row.group_id,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/repositories/test_task_repository.py -v
```
Expected: all PASS (existing tests plus the 3 new ones).

- [ ] **Step 5: Commit**

```bash
git add app/repositories/task_repository.py tests/repositories/test_task_repository.py
git commit -m "feat: map groupId in TaskRepository, add list_by_group"
```

---

## Task 4: `TaskService.create_task` — accept `groupId`, validate membership, auto-assign creator

**Files:**
- Modify: `app/services/task_service.py`
- Modify: `app/dependencies.py`
- Modify: `tests/conftest.py`
- Modify: `tests/unit/test_task_service.py`

**Interfaces:**
- Consumes: `TaskRepository.list_by_group` (Task 3), `GroupService.get_group(group_id, current_user_id=...)` (existing, in `app/services/group_service.py`), `TaskGroupRepository.add` (existing), `TaskGroupRelationship` (existing, `app/models/task_group.py`).
- Produces: `TaskService.__init__(repository, user_service, task_group_repository, group_service)` (new 4th constructor arg — every fixture/provider that builds a `TaskService` must be updated), `TaskService.create_task(..., group_id: Optional[str] = None)`, `TaskService.list_tasks_by_group(group_id: str) -> list[Task]` — consumed by Task 8 (`TaskGroupService.list_tasks_for_group`) and Task 9 (router).

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_task_service.py`, add `GroupService`/`GroupRepository`/`UserGroupRepository` imports (already partially imported by `test_task_group_service.py`'s style — add explicitly here):

```python
from app.repositories.group_repository import GroupRepository
from app.repositories.user_group_repository import UserGroupRepository
from app.services.group_service import GroupService
```

Add a `group_service` fixture and thread it into `task_service` (both go **above** the existing `task_service` fixture definition):

```python
@pytest.fixture
def group_service(db_session, user_service: UserService) -> GroupService:
    return GroupService(GroupRepository(db_session), user_service, UserGroupRepository(db_session))


@pytest.fixture
def task_service(db_session, user_service: UserService, group_service: GroupService) -> TaskService:
    return TaskService(
        TaskRepository(db_session), user_service, TaskGroupRepository(db_session), group_service
    )
```

Add new tests (needs `UserGroupService` too for the "member, not creator" case — import it and build inline, matching `test_task_group_service.py`'s style):

```python
from app.repositories.task_group_repository import TaskGroupRepository as _TaskGroupRepoForAssert
from app.services.user_group_service import UserGroupService


def test_create_task_with_group_id_sets_group_id_and_auto_assigns_creator(
    task_service: TaskService, user_service: UserService, group_service: GroupService, db_session
):
    creator = user_service.create_user(user_id="ada", first_name="Ada", last_name="Lovelace")
    group = group_service.create_group(
        group_name="Smiths", group_desc=None, group_category="Family", creater_id=creator.userId
    )

    task = task_service.create_task(task_title="Buy milk", created_by=creator.userId, group_id=group.groupId)

    assert task.groupId == group.groupId
    relationship = _TaskGroupRepoForAssert(db_session).find_by_task_and_group(task.taskId, group.groupId)
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
    relationship = _TaskGroupRepoForAssert(db_session).find_by_task_and_group(task.taskId, group.groupId)
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/unit/test_task_service.py -v
```
Expected: new tests FAIL with `TypeError: TaskService.__init__() takes 4 positional arguments but 5 were given` (or `create_task() got an unexpected keyword argument 'group_id'` / `AttributeError: 'TaskService' object has no attribute 'list_tasks_by_group'`).

- [ ] **Step 3: Implement — edit `app/services/task_service.py`**

Full replacement content:

```python
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.exceptions import BadRequestError, ErrorCode, ForbiddenError, NotFoundError
from app.models.enums import TaskState
from app.models.task import Task
from app.models.task_group import TaskGroupRelationship
from app.repositories.base import BaseRepository
from app.repositories.task_group_repository import TaskGroupRepository
from app.services.group_service import GroupService
from app.services.user_service import UserService


class TaskService:
    def __init__(
        self,
        repository: BaseRepository[Task],
        user_service: UserService,
        task_group_repository: TaskGroupRepository,
        group_service: GroupService,
    ):
        self._repository = repository
        self._user_service = user_service
        self._task_group_repository = task_group_repository
        self._group_service = group_service

    def create_task(
        self,
        task_title: str,
        created_by: str,
        task_desc: Optional[str] = None,
        task_due_date: Optional[datetime] = None,
        group_id: Optional[str] = None,
    ) -> Task:
        self._user_service.get_user(created_by)
        if group_id is not None:
            # Raises NotFoundError if the group doesn't exist, ForbiddenError
            # if created_by is neither the group's creator nor a member.
            self._group_service.get_group(group_id, current_user_id=created_by)
        now = datetime.now(timezone.utc)
        task = Task(
            taskId=str(uuid.uuid4()),
            taskTitle=task_title,
            taskDesc=task_desc,
            taskDueDate=task_due_date,
            taskState=TaskState.TODO,
            createdAt=now,
            createdBy=created_by,
            updatedAt=None,
            updatedBy=None,
            groupId=group_id,
        )
        created = self._repository.add(task)
        if group_id is not None:
            # Auto-bootstrap the task-group assignment with assignee = creator.
            # Inserted directly (bypassing TaskGroupService.assign()) because a
            # group's own creator can never be a UserGroupRelationship member
            # row, which would otherwise fail assign()'s is_member check even
            # though the creator is a legitimate task creator here.
            relationship = TaskGroupRelationship(
                uuid=str(uuid.uuid4()),
                taskId=created.taskId,
                groupId=group_id,
                assigneeId=created_by,
            )
            self._task_group_repository.add(relationship)
        return created

    def get_task(self, task_id: str, current_user_id: Optional[str] = None) -> Task:
        task = self._repository.get(task_id)
        if task is None:
            raise NotFoundError(f"Task {task_id} not found")
        if current_user_id is not None and current_user_id != task.createdBy:
            assignments = self._task_group_repository.list_by_task(task_id)
            is_assignee = any(rel.assigneeId == current_user_id for rel in assignments)
            if not is_assignee:
                raise ForbiddenError(f"User {current_user_id} is not authorized to access task {task_id}")
        return task

    def update_task_meta(
        self,
        task_id: str,
        updated_by: str,
        task_title: Optional[str] = None,
        task_desc: Optional[str] = None,
        current_user_id: Optional[str] = None,
    ) -> Task:
        self._user_service.get_user(updated_by)
        task = self.get_task(task_id)
        if current_user_id is not None and current_user_id != task.createdBy:
            raise ForbiddenError(f"User {current_user_id} is not authorized to update task {task_id}")
        updated = task.model_copy(
            update={
                "taskTitle": task_title if task_title is not None else task.taskTitle,
                "taskDesc": task_desc if task_desc is not None else task.taskDesc,
                "updatedBy": updated_by,
                "updatedAt": datetime.now(timezone.utc),
            }
        )
        return self._repository.update(updated)

    def update_task_state(
        self, task_id: str, updated_by: str, new_state: TaskState, current_user_id: Optional[str] = None
    ) -> Task:
        self._user_service.get_user(updated_by)
        task = self.get_task(task_id, current_user_id=current_user_id)
        if task.taskState == new_state:
            raise BadRequestError(ErrorCode.TASK_ALREADY_IN_REQUESTED_STATE)
        updated = task.model_copy(
            update={
                "taskState": new_state,
                "updatedBy": updated_by,
                "updatedAt": datetime.now(timezone.utc),
            }
        )
        return self._repository.update(updated)

    def update_due_date(
        self,
        task_id: str,
        updated_by: str,
        due_date: Optional[datetime],
        current_user_id: Optional[str] = None,
    ) -> Task:
        self._user_service.get_user(updated_by)
        task = self.get_task(task_id, current_user_id=current_user_id)
        updated = task.model_copy(
            update={
                "taskDueDate": due_date,
                "updatedBy": updated_by,
                "updatedAt": datetime.now(timezone.utc),
            }
        )
        return self._repository.update(updated)

    def get_tasks_for_user(self, current_user_id: str) -> list[Task]:
        created = self._repository.list_by_creator(current_user_id)
        seen_ids = {t.taskId for t in created}
        assigned_tasks = []
        for rel in self._task_group_repository.list_by_assignee(current_user_id):
            if rel.taskId in seen_ids:
                continue
            task = self._repository.get(rel.taskId)
            if task is not None:
                assigned_tasks.append(task)
                seen_ids.add(rel.taskId)
        all_tasks = created + assigned_tasks
        all_tasks.sort(key=lambda t: t.updatedAt or t.createdAt, reverse=True)
        return all_tasks

    def list_tasks_by_group(self, group_id: str) -> list[Task]:
        return self._repository.list_by_group(group_id)
```

Note: `update_task_meta`/`update_task_state`/`update_due_date` still take `updated_by` here — Task 5 changes that signature. Keeping this task focused on `create_task`/`list_tasks_by_group` only.

- [ ] **Step 3b: Wire the new dependency — edit `app/dependencies.py`**

Change only `get_task_service`:

```python
def get_task_service(
    repository: TaskRepository = Depends(get_task_repository),
    user_service: UserService = Depends(get_user_service),
    task_group_repository: TaskGroupRepository = Depends(get_task_group_repository),
    group_service: GroupService = Depends(get_group_service),
) -> TaskService:
    return TaskService(repository, user_service, task_group_repository, group_service)
```

- [ ] **Step 3c: Update fixtures — edit `tests/conftest.py`**

In both the `client` and `unauthenticated_client` fixtures, change:
```python
task_service = TaskService(task_repo, user_service, task_group_repo)
```
to:
```python
task_service = TaskService(task_repo, user_service, task_group_repo, group_service)
```
(`group_service` is already constructed earlier in each fixture body — no new import needed.)

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/unit/test_task_service.py -v
```
Expected: all PASS, including the 5 new tests. (Other unit/integration suites may still be red until later tasks — that's expected; don't run the full suite yet.)

- [ ] **Step 5: Commit**

```bash
git add app/services/task_service.py app/dependencies.py tests/conftest.py tests/unit/test_task_service.py
git commit -m "feat: TaskService.create_task accepts groupId, validates membership, auto-assigns creator"
```

---

## Task 5: `TaskService` update methods — derive `updatedBy` from `current_user_id`

**Files:**
- Modify: `app/services/task_service.py`
- Modify: `tests/unit/test_task_service.py`

**Interfaces:**
- Produces: `update_task_meta(task_id, current_user_id, task_title=None, task_desc=None)`, `update_task_state(task_id, current_user_id, new_state)`, `update_due_date(task_id, current_user_id, due_date)` — `updated_by` parameter removed, `current_user_id` is now required (not `Optional`). Consumed by Task 9 (router).

- [ ] **Step 1: Update the tests**

In `tests/unit/test_task_service.py`, rename every `updated_by=user.userId` kwarg to `current_user_id=user.userId` across these call sites (search for `updated_by=` — there are roughly a dozen): `test_update_task_meta_changes_title_and_desc`, `test_update_task_state_transitions`, `test_update_task_state_raises_bad_request_if_already_completed` (both calls), `test_update_task_state_raises_bad_request_if_same_state_requested`, `test_update_task_state_allows_moving_out_of_completed` (both calls), `test_update_due_date`, `test_update_due_date_clears_existing_due_date` (both calls).

Example of the transformation (repeat for every call site listed above):
```python
# before
updated = task_service.update_task_meta(
    task.taskId, updated_by=user.userId, task_title="Buy oat milk", task_desc="2 liters"
)
# after
updated = task_service.update_task_meta(
    task.taskId, current_user_id=user.userId, task_title="Buy oat milk", task_desc="2 liters"
)
```

For `test_update_task_meta_raises_forbidden_if_caller_is_not_creator`, change:
```python
# before
task_service.update_task_meta(
    task.taskId, updated_by=user.userId, task_title="New", current_user_id="outsider"
)
# after
task_service.update_task_meta(
    task.taskId, current_user_id="outsider", task_title="New"
)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/unit/test_task_service.py -v
```
Expected: `TypeError: TaskService.update_task_meta() got an unexpected keyword argument 'current_user_id'` (or similar) for every renamed call — the service still expects `updated_by`.

- [ ] **Step 3: Implement — edit `app/services/task_service.py`**

Replace the three update methods:

```python
    def update_task_meta(
        self,
        task_id: str,
        current_user_id: str,
        task_title: Optional[str] = None,
        task_desc: Optional[str] = None,
    ) -> Task:
        self._user_service.get_user(current_user_id)
        task = self.get_task(task_id)
        if current_user_id != task.createdBy:
            raise ForbiddenError(f"User {current_user_id} is not authorized to update task {task_id}")
        updated = task.model_copy(
            update={
                "taskTitle": task_title if task_title is not None else task.taskTitle,
                "taskDesc": task_desc if task_desc is not None else task.taskDesc,
                "updatedBy": current_user_id,
                "updatedAt": datetime.now(timezone.utc),
            }
        )
        return self._repository.update(updated)

    def update_task_state(self, task_id: str, current_user_id: str, new_state: TaskState) -> Task:
        self._user_service.get_user(current_user_id)
        task = self.get_task(task_id, current_user_id=current_user_id)
        if task.taskState == new_state:
            raise BadRequestError(ErrorCode.TASK_ALREADY_IN_REQUESTED_STATE)
        updated = task.model_copy(
            update={
                "taskState": new_state,
                "updatedBy": current_user_id,
                "updatedAt": datetime.now(timezone.utc),
            }
        )
        return self._repository.update(updated)

    def update_due_date(
        self, task_id: str, current_user_id: str, due_date: Optional[datetime]
    ) -> Task:
        self._user_service.get_user(current_user_id)
        task = self.get_task(task_id, current_user_id=current_user_id)
        updated = task.model_copy(
            update={
                "taskDueDate": due_date,
                "updatedBy": current_user_id,
                "updatedAt": datetime.now(timezone.utc),
            }
        )
        return self._repository.update(updated)
```

(Preserves the existing creator-only vs. creator-or-assignee asymmetry exactly — only the source of `updatedBy`/authorization value changed.)

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/unit/test_task_service.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/task_service.py tests/unit/test_task_service.py
git commit -m "feat: derive Task updatedBy from current_user_id instead of a separate request param"
```

---

## Task 6: `TaskGroupService.assign` — retire the creator-cannot-be-assignee rule

**Files:**
- Modify: `app/services/task_group_service.py`
- Modify: `tests/unit/test_task_group_service.py`
- Modify: `tests/integration/test_task_group_api.py`

**Interfaces:**
- Consumes: nothing new.
- Removes: the `assignee_id == task.createdBy` check inside `assign()`.

- [ ] **Step 1: Update the tests**

In `tests/unit/test_task_group_service.py`, replace `test_assign_raises_bad_request_if_assignee_is_task_creator`:

```python
def test_assign_to_creator_now_succeeds(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    creator, assignee, group, task = _setup(user_service, group_service, task_service, user_group_service)
    relationship = task_group_service.assign(task.taskId, group.groupId, creator.userId)
    assert relationship.assigneeId == creator.userId
```

In `tests/integration/test_task_group_api.py`, replace `test_assign_task_to_creator_returns_400`:

```python
def test_assign_task_to_creator_now_succeeds(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    group_id = _create_group(client, authenticate_as, creator_id)
    task_id = _create_task(client, authenticate_as, creator_id)

    response = client.post(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": creator_id}
    )
    assert response.status_code == 201
    assert response.json()["assigneeId"] == creator_id
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/unit/test_task_group_service.py::test_assign_to_creator_now_succeeds tests/integration/test_task_group_api.py::test_assign_task_to_creator_now_succeeds -v
```
Expected: both FAIL — the service still raises `BadRequestError` for this case (unit test raises unexpectedly; integration test gets 400 not 201).

- [ ] **Step 3: Implement — edit `app/services/task_group_service.py`**

In `assign()`, delete this block entirely:
```python
        if assignee_id == task.createdBy:
            raise BadRequestError(ErrorCode.TASK_CREATOR_CANNOT_BE_ASSIGNEE)
```
So `assign()` becomes:
```python
    def assign(
        self, task_id: str, group_id: str, assignee_id: str, current_user_id: Optional[str] = None
    ) -> TaskGroupRelationship:
        task = self._task_service.get_task(task_id)
        self._group_service.get_group(group_id)
        self._user_service.get_user(assignee_id)
        if current_user_id is not None and current_user_id != task.createdBy:
            raise ForbiddenError(f"User {current_user_id} is not authorized to assign task {task_id}")
        if not self._user_group_service.is_member(assignee_id, group_id):
            raise BadRequestError(ErrorCode.ASSIGNEE_NOT_GROUP_MEMBER)

        existing = self._repository.find_by_task_and_group(task_id, group_id)
        if existing is not None:
            updated = existing.model_copy(update={"assigneeId": assignee_id})
            return self._repository.update(updated)
        entity = TaskGroupRelationship(
            uuid=str(uuid.uuid4()), taskId=task_id, groupId=group_id, assigneeId=assignee_id
        )
        return self._repository.add(entity)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/unit/test_task_group_service.py tests/integration/test_task_group_api.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/task_group_service.py tests/unit/test_task_group_service.py tests/integration/test_task_group_api.py
git commit -m "feat: allow a task's creator to be their own assignee (retire ERR_TASKS_005)"
```

---

## Task 7: `TaskGroupService` — remove `unassign`, add `reassign`

**Files:**
- Modify: `app/services/task_group_service.py`
- Modify: `tests/unit/test_task_group_service.py`

**Interfaces:**
- Removes: `unassign(task_id, group_id, assignee_id, current_user_id=None)`.
- Produces: `reassign(task_id, group_id, assignee_id, current_user_id=None) -> TaskGroupRelationship` — consumed by Task 10 (router).

- [ ] **Step 1: Update the tests**

In `tests/unit/test_task_group_service.py`, delete these four tests entirely: `test_unassign_clears_assignee`, `test_unassign_raises_if_no_matching_assignment`, `test_unassign_raises_if_assignee_does_not_match_current_assignment`, `test_unassign_raises_forbidden_if_caller_is_not_task_creator`.

Add new tests for `reassign`:

```python
def test_reassign_updates_assignee_to_new_group_member(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    creator, assignee, group, task = _setup(user_service, group_service, task_service, user_group_service)
    other_member = user_service.create_user(user_id="cara", first_name="Cara", last_name="Jones")
    user_group_service.associate(other_member.userId, group.groupId, "Member")
    task_group_service.assign(task.taskId, group.groupId, assignee.userId)

    result = task_group_service.reassign(task.taskId, group.groupId, other_member.userId)

    assert result.assigneeId == other_member.userId


def test_reassign_raises_bad_request_if_same_as_current_assignee(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    _, assignee, group, task = _setup(user_service, group_service, task_service, user_group_service)
    task_group_service.assign(task.taskId, group.groupId, assignee.userId)

    with pytest.raises(BadRequestError) as exc_info:
        task_group_service.reassign(task.taskId, group.groupId, assignee.userId)
    assert exc_info.value.error_code == ErrorCode.REASSIGN_ASSIGNEE_UNCHANGED
    assert exc_info.value.http_code == 400


def test_reassign_raises_bad_request_if_new_assignee_not_group_member(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    creator, assignee, group, task = _setup(user_service, group_service, task_service, user_group_service)
    outsider = user_service.create_user(user_id="cara", first_name="Cara", last_name="Jones")
    task_group_service.assign(task.taskId, group.groupId, assignee.userId)

    with pytest.raises(BadRequestError) as exc_info:
        task_group_service.reassign(task.taskId, group.groupId, outsider.userId)
    assert exc_info.value.error_code == ErrorCode.REASSIGN_ASSIGNEE_NOT_GROUP_MEMBER
    assert exc_info.value.http_code == 400


def test_reassign_raises_not_found_if_no_existing_assignment(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    _, assignee, group, task = _setup(user_service, group_service, task_service, user_group_service)
    with pytest.raises(NotFoundError):
        task_group_service.reassign(task.taskId, group.groupId, assignee.userId)


def test_reassign_succeeds_for_plain_member_caller(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    creator, assignee, group, task = _setup(user_service, group_service, task_service, user_group_service)
    task_group_service.assign(task.taskId, group.groupId, assignee.userId)

    result = task_group_service.reassign(
        task.taskId, group.groupId, creator.userId, current_user_id=assignee.userId
    )
    assert result.assigneeId == creator.userId


def test_reassign_succeeds_for_creator_caller(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    creator, assignee, group, task = _setup(user_service, group_service, task_service, user_group_service)
    task_group_service.assign(task.taskId, group.groupId, assignee.userId)

    result = task_group_service.reassign(
        task.taskId, group.groupId, creator.userId, current_user_id=creator.userId
    )
    assert result.assigneeId == creator.userId


def test_reassign_raises_forbidden_if_caller_is_not_a_group_member(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    creator, assignee, group, task = _setup(user_service, group_service, task_service, user_group_service)
    task_group_service.assign(task.taskId, group.groupId, assignee.userId)

    with pytest.raises(ForbiddenError):
        task_group_service.reassign(
            task.taskId, group.groupId, creator.userId, current_user_id="outsider"
        )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/unit/test_task_group_service.py -v
```
Expected: the deleted-test names no longer collected (fine); the new `reassign` tests FAIL with `AttributeError: 'TaskGroupService' object has no attribute 'reassign'`.

- [ ] **Step 3: Implement — edit `app/services/task_group_service.py`**

Delete `unassign()` entirely. Add `reassign()` (place it directly after `assign()`):

```python
    def reassign(
        self,
        task_id: str,
        group_id: str,
        assignee_id: str,
        current_user_id: Optional[str] = None,
    ) -> TaskGroupRelationship:
        self._task_service.get_task(task_id)
        # Creator-or-member (same rule as GroupService.get_group elsewhere) —
        # deliberately not creator-only, unlike assign(). Raises NotFoundError
        # if the group doesn't exist, ForbiddenError if caller is neither.
        self._group_service.get_group(group_id, current_user_id=current_user_id)
        self._user_service.get_user(assignee_id)

        existing = self._repository.find_by_task_and_group(task_id, group_id)
        if existing is None:
            raise NotFoundError(f"No existing assignment for task {task_id} in group {group_id}")
        if assignee_id == existing.assigneeId:
            raise BadRequestError(ErrorCode.REASSIGN_ASSIGNEE_UNCHANGED)
        if not self._user_group_service.is_member(assignee_id, group_id):
            raise BadRequestError(ErrorCode.REASSIGN_ASSIGNEE_NOT_GROUP_MEMBER)

        updated = existing.model_copy(update={"assigneeId": assignee_id})
        return self._repository.update(updated)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/unit/test_task_group_service.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/task_group_service.py tests/unit/test_task_group_service.py
git commit -m "feat: remove TaskGroupService.unassign, add reassign (creator-or-member authorized)"
```

---

## Task 8: `TaskGroupService.list_tasks_for_group`

**Files:**
- Modify: `app/services/task_group_service.py`
- Modify: `tests/unit/test_task_group_service.py`

**Interfaces:**
- Consumes: `TaskService.list_tasks_by_group` (Task 4), `GroupService.get_group` (existing).
- Produces: `list_tasks_for_group(group_id, current_user_id=None) -> list[Task]` — consumed by Task 10 (router).

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_task_group_service.py`:

```python
def test_list_tasks_for_group_returns_tasks_for_creator_caller(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    creator, assignee, group, task = _setup(user_service, group_service, task_service, user_group_service)
    results = task_group_service.list_tasks_for_group(group.groupId, current_user_id=creator.userId)
    assert [t.taskId for t in results] == [task.taskId]


def test_list_tasks_for_group_returns_tasks_for_member_caller(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    creator, assignee, group, task = _setup(user_service, group_service, task_service, user_group_service)
    results = task_group_service.list_tasks_for_group(group.groupId, current_user_id=assignee.userId)
    assert [t.taskId for t in results] == [task.taskId]


def test_list_tasks_for_group_raises_forbidden_for_non_member_non_creator(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    creator, assignee, group, task = _setup(user_service, group_service, task_service, user_group_service)
    with pytest.raises(ForbiddenError):
        task_group_service.list_tasks_for_group(group.groupId, current_user_id="outsider")


def test_list_tasks_for_group_raises_not_found_for_unknown_group(task_group_service):
    with pytest.raises(NotFoundError):
        task_group_service.list_tasks_for_group("unknown-group")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/unit/test_task_group_service.py -v
```
Expected: the 4 new tests FAIL with `AttributeError: 'TaskGroupService' object has no attribute 'list_tasks_for_group'`.

- [ ] **Step 3: Implement — edit `app/services/task_group_service.py`**

Add this method (place after `reassign()`):

```python
    def list_tasks_for_group(self, group_id: str, current_user_id: Optional[str] = None) -> list[Task]:
        self._group_service.get_group(group_id, current_user_id=current_user_id)
        return self._task_service.list_tasks_by_group(group_id)
```

Add `from app.models.task import Task` to the file's imports.

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/unit/test_task_group_service.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/task_group_service.py tests/unit/test_task_group_service.py
git commit -m "feat: add TaskGroupService.list_tasks_for_group (creator-or-member authorized)"
```

---

## Task 9: `app/api/v1/tasks.py` — wire `groupId` and token-derived `updatedBy`

**Files:**
- Modify: `app/api/v1/tasks.py`
- Modify: `tests/integration/test_tasks_api.py`

**Interfaces:**
- Consumes: `TaskService.create_task(..., group_id=...)` (Task 4), `TaskService.update_task_meta/update_task_state/update_due_date(task_id, current_user_id, ...)` (Task 5).
- Produces: `POST /api/v1/tasks` accepts `groupId`; PATCH routes no longer accept `updatedBy` in the body.

- [ ] **Step 1: Update the tests**

In `tests/integration/test_tasks_api.py`, remove `"updatedBy": user_id` from every PATCH JSON payload dict — the affected tests are `test_update_task_meta`, `test_update_task_meta_non_creator_returns_403`, `test_update_task_state`, `test_update_task_state_already_completed_returns_400` (both calls), `test_update_task_state_allows_moving_out_of_completed` (both calls), `test_update_task_due_date`, `test_update_task_due_date_to_null_clears_it` (both calls), `test_update_task_state_same_state_returns_400`.

Example transformation:
```python
# before
response = client.patch(
    f"/api/v1/tasks/{task_id}", json={"updatedBy": user_id, "taskTitle": "Buy oat milk"}
)
# after
response = client.patch(f"/api/v1/tasks/{task_id}", json={"taskTitle": "Buy oat milk"})
```

Add new tests:

```python
def test_create_task_with_group_id_returns_group_id_in_response(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    group_id = client.post(
        "/api/v1/groups", json={"groupName": "Smiths", "groupCategory": "Family"}
    ).json()["groupId"]

    response = client.post("/api/v1/tasks", json={"taskTitle": "Buy milk", "groupId": group_id})
    assert response.status_code == 201
    assert response.json()["groupId"] == group_id


def test_create_task_with_unknown_group_id_returns_404(client, authenticate_as):
    _create_user(client, authenticate_as, "creator")
    response = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "groupId": "unknown-group"}
    )
    assert response.status_code == 404


def test_create_task_with_group_id_non_member_returns_403(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    group_id = client.post(
        "/api/v1/groups", json={"groupName": "Smiths", "groupCategory": "Family"}
    ).json()["groupId"]

    authenticate_as("outsider")
    response = client.post("/api/v1/tasks", json={"taskTitle": "Buy milk", "groupId": group_id})
    assert response.status_code == 403


def test_get_task_returns_group_id_field(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    group_id = client.post(
        "/api/v1/groups", json={"groupName": "Smiths", "groupCategory": "Family"}
    ).json()["groupId"]
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "groupId": group_id}
    ).json()["taskId"]

    response = client.get(f"/api/v1/tasks/{task_id}")
    assert response.json()["groupId"] == group_id


def test_update_task_meta_cannot_change_group_id(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    group_id = client.post(
        "/api/v1/groups", json={"groupName": "Smiths", "groupCategory": "Family"}
    ).json()["groupId"]
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "groupId": group_id}
    ).json()["taskId"]

    response = client.patch(
        f"/api/v1/tasks/{task_id}", json={"taskTitle": "Buy oat milk", "groupId": "other-group"}
    )
    assert response.status_code == 200
    assert response.json()["groupId"] == group_id
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/integration/test_tasks_api.py -v
```
Expected: the renamed-payload PATCH tests still pass superficially wrong (router still reads `payload.updatedBy` which no longer exists on the schema after Task 9's schema edit hasn't happened yet — actually run this AFTER updating `app/schemas/task.py`, see note below) — new `groupId` tests FAIL (`groupId` not accepted/returned).

  **Note:** This task assumes `app/schemas/task.py` already has `groupId` on `TaskCreateRequest`/`TaskResponse` and no `updatedBy` on the three update schemas — if not yet applied, apply this schema edit as part of Step 3 below (it belongs here since Tasks 1-8 didn't touch schemas).

- [ ] **Step 3: Implement**

**3a. Edit `app/schemas/task.py`** (full replacement content):

```python
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.enums import TaskState


class TaskCreateRequest(BaseModel):
    taskTitle: str
    taskDesc: Optional[str] = None
    taskDueDate: Optional[datetime] = None
    groupId: Optional[str] = None


class TaskMetaUpdateRequest(BaseModel):
    taskTitle: Optional[str] = None
    taskDesc: Optional[str] = None


class TaskStateUpdateRequest(BaseModel):
    taskState: TaskState


class TaskDueDateUpdateRequest(BaseModel):
    taskDueDate: Optional[datetime] = None


class TaskResponse(BaseModel):
    taskId: str
    taskTitle: str
    taskDesc: Optional[str] = None
    taskDueDate: Optional[datetime] = None
    taskState: TaskState
    createdAt: datetime
    createdBy: str
    updatedAt: Optional[datetime] = None
    updatedBy: Optional[str] = None
    groupId: Optional[str] = None
```

**3b. Edit `app/api/v1/tasks.py`** — `create_task`:

```python
@router.post(
    "",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"description": "Task creator (user) or groupId not found"},
        403: {"description": "Not authorized to create a task in that group"},
    },
)
def create_task(
    payload: TaskCreateRequest,
    current_user_id: str = Depends(verify_firebase_token),
    service: TaskService = Depends(get_task_service),
) -> TaskResponse:
    try:
        task = service.create_task(
            task_title=payload.taskTitle,
            created_by=current_user_id,
            task_desc=payload.taskDesc,
            task_due_date=payload.taskDueDate,
            group_id=payload.groupId,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return _to_response(task)
```

**3c. Edit `app/api/v1/tasks.py`** — the three PATCH routes, replace their service calls:

```python
def update_task_meta(
    task_id: str,
    payload: TaskMetaUpdateRequest,
    current_user_id: str = Depends(verify_firebase_token),
    service: TaskService = Depends(get_task_service),
) -> TaskResponse:
    try:
        task = service.update_task_meta(
            task_id,
            current_user_id=current_user_id,
            task_title=payload.taskTitle,
            task_desc=payload.taskDesc,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return _to_response(task)
```

```python
def update_task_state(
    task_id: str,
    payload: TaskStateUpdateRequest,
    current_user_id: str = Depends(verify_firebase_token),
    service: TaskService = Depends(get_task_service),
) -> TaskResponse:
    try:
        task = service.update_task_state(
            task_id,
            current_user_id=current_user_id,
            new_state=payload.taskState,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BadRequestError as exc:
        raise HTTPException(
            status_code=exc.http_code,
            detail=ErrorDetail(errorCode=exc.error_code, message=exc.message).model_dump(),
        ) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return _to_response(task)
```

```python
def update_due_date(
    task_id: str,
    payload: TaskDueDateUpdateRequest,
    current_user_id: str = Depends(verify_firebase_token),
    service: TaskService = Depends(get_task_service),
) -> TaskResponse:
    try:
        task = service.update_due_date(
            task_id,
            current_user_id=current_user_id,
            due_date=payload.taskDueDate,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return _to_response(task)
```

(`get_task`, `list_my_tasks`, `_to_response` are unchanged — `groupId` flows through `TaskResponse(**task.model_dump())` automatically.)

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/integration/test_tasks_api.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/schemas/task.py app/api/v1/tasks.py tests/integration/test_tasks_api.py
git commit -m "feat: POST /api/v1/tasks accepts groupId, PATCH routes derive updatedBy from the token"
```

---

## Task 10: `app/api/v1/task_group.py` + `app/main.py` — remove DELETE, add PATCH reassign + GET group-tasks

**Files:**
- Modify: `app/api/v1/task_group.py`
- Modify: `app/main.py`
- Modify: `tests/integration/test_task_group_api.py`

**Interfaces:**
- Consumes: `TaskGroupService.reassign` (Task 7), `TaskGroupService.list_tasks_for_group` (Task 8).
- Produces: `PATCH /api/v1/groups/{group_id}/tasks/{task_id}/assignee`, `GET /api/v1/groups/{group_id}/tasks`. Removes `DELETE /api/v1/groups/{groupId}/tasks/{taskId}/assignee/{assigneeId}`.

- [ ] **Step 1: Update/add the tests**

In `tests/integration/test_task_group_api.py`, delete these four tests entirely: `test_unassign_task`, `test_unassign_task_wrong_caller_returns_403`, `test_unassign_task_without_prior_assignment_returns_404`, `test_unassign_task_with_mismatched_assignee_returns_404`.

Add:

```python
def test_delete_assignee_route_removed_returns_404(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    group_id = _create_group(client, authenticate_as, creator_id)
    task_id = _create_task(client, authenticate_as, creator_id)
    response = client.delete(f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee/{creator_id}")
    assert response.status_code == 404


def test_reassign_task_to_new_member_succeeds(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    member_id = _create_user(client, authenticate_as, "member", first_name="Bob", last_name="Smith")
    other_member_id = _create_user(client, authenticate_as, "other", first_name="Cara", last_name="Jones")
    group_id = _create_group(client, authenticate_as, creator_id)
    task_id = _create_task(client, authenticate_as, creator_id)
    _associate_user(client, group_id, member_id)
    _associate_user(client, group_id, other_member_id)
    client.post(f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": member_id})

    response = client.patch(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": other_member_id}
    )
    assert response.status_code == 200
    assert response.json()["assigneeId"] == other_member_id


def test_reassign_task_same_assignee_returns_400_err_007(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    member_id = _create_user(client, authenticate_as, "member", first_name="Bob", last_name="Smith")
    group_id = _create_group(client, authenticate_as, creator_id)
    task_id = _create_task(client, authenticate_as, creator_id)
    _associate_user(client, group_id, member_id)
    client.post(f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": member_id})

    response = client.patch(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": member_id}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["errorCode"] == "ERR_TASKS_007"


def test_reassign_task_non_member_returns_400_err_008(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    member_id = _create_user(client, authenticate_as, "member", first_name="Bob", last_name="Smith")
    outsider_id = _create_user(client, authenticate_as, "outsider", first_name="Cara", last_name="Jones")
    group_id = _create_group(client, authenticate_as, creator_id)
    task_id = _create_task(client, authenticate_as, creator_id)
    _associate_user(client, group_id, member_id)
    client.post(f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": member_id})

    response = client.patch(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": outsider_id}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["errorCode"] == "ERR_TASKS_008"


def test_reassign_task_any_member_can_call_not_just_creator(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    member_id = _create_user(client, authenticate_as, "member", first_name="Bob", last_name="Smith")
    group_id = _create_group(client, authenticate_as, creator_id)
    task_id = _create_task(client, authenticate_as, creator_id)
    _associate_user(client, group_id, member_id)
    client.post(f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": member_id})

    authenticate_as(member_id)
    response = client.patch(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": creator_id}
    )
    assert response.status_code == 200
    assert response.json()["assigneeId"] == creator_id


def test_reassign_task_non_member_caller_returns_403(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    member_id = _create_user(client, authenticate_as, "member", first_name="Bob", last_name="Smith")
    group_id = _create_group(client, authenticate_as, creator_id)
    task_id = _create_task(client, authenticate_as, creator_id)
    _associate_user(client, group_id, member_id)
    client.post(f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": member_id})

    authenticate_as("outsider")
    response = client.patch(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": creator_id}
    )
    assert response.status_code == 403


def test_list_group_tasks_as_creator(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    group_id = _create_group(client, authenticate_as, creator_id)
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "groupId": group_id}
    ).json()["taskId"]

    response = client.get(f"/api/v1/groups/{group_id}/tasks")
    assert response.status_code == 200
    assert [t["taskId"] for t in response.json()] == [task_id]


def test_list_group_tasks_as_member(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    member_id = _create_user(client, authenticate_as, "member", first_name="Bob", last_name="Smith")
    group_id = _create_group(client, authenticate_as, creator_id)
    _associate_user(client, group_id, member_id)
    client.post("/api/v1/tasks", json={"taskTitle": "Buy milk", "groupId": group_id})

    authenticate_as(member_id)
    response = client.get(f"/api/v1/groups/{group_id}/tasks")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_list_group_tasks_non_member_returns_403(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    group_id = _create_group(client, authenticate_as, creator_id)

    authenticate_as("outsider")
    response = client.get(f"/api/v1/groups/{group_id}/tasks")
    assert response.status_code == 403


def test_list_group_tasks_unknown_group_returns_404(client, authenticate_as):
    _create_user(client, authenticate_as, "creator")
    response = client.get("/api/v1/groups/unknown-group/tasks")
    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/integration/test_task_group_api.py -v
```
Expected: `test_delete_assignee_route_removed_returns_404` currently PASSES-as-201-fails-assert (DELETE route still exists) — actually FAILS since it currently returns 200, not 404; all `test_reassign_*` and `test_list_group_tasks_*` tests FAIL with 404/405 (routes don't exist yet).

- [ ] **Step 3: Implement — edit `app/api/v1/task_group.py`** (full replacement content)

```python
from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import verify_firebase_token
from app.dependencies import get_task_group_service
from app.exceptions import BadRequestError, ForbiddenError, NotFoundError
from app.schemas.errors import BadRequestResponse, ErrorDetail
from app.schemas.task import TaskResponse
from app.schemas.task_group import TaskGroupAssignRequest, TaskGroupResponse
from app.services.task_group_service import TaskGroupService

router = APIRouter(prefix="/api/v1/groups/{group_id}/tasks/{task_id}/assignee", tags=["task-group"])

group_tasks_router = APIRouter(prefix="/api/v1/groups/{group_id}/tasks", tags=["task-group"])


@router.post(
    "",
    response_model=TaskGroupResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"description": "Task, Group, or Assignee (user) not found"},
        400: {
            "model": BadRequestResponse,
            "description": "Assignee is not a member of the target group",
        },
        403: {"description": "Not authorized"},
    },
)
def assign_task(
    group_id: str,
    task_id: str,
    payload: TaskGroupAssignRequest,
    current_user_id: str = Depends(verify_firebase_token),
    service: TaskGroupService = Depends(get_task_group_service),
) -> TaskGroupResponse:
    try:
        relationship = service.assign(
            task_id, group_id, payload.assigneeId, current_user_id=current_user_id
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BadRequestError as exc:
        raise HTTPException(
            status_code=exc.http_code,
            detail=ErrorDetail(errorCode=exc.error_code, message=exc.message).model_dump(),
        ) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return TaskGroupResponse(**relationship.model_dump())


@router.patch(
    "",
    response_model=TaskGroupResponse,
    responses={
        404: {"description": "Task, Group, Assignee (user), or existing assignment not found"},
        400: {
            "model": BadRequestResponse,
            "description": "Requested assignee is same as current assignee, or not a group member",
        },
        403: {"description": "Not authorized"},
    },
)
def reassign_task(
    group_id: str,
    task_id: str,
    payload: TaskGroupAssignRequest,
    current_user_id: str = Depends(verify_firebase_token),
    service: TaskGroupService = Depends(get_task_group_service),
) -> TaskGroupResponse:
    try:
        relationship = service.reassign(
            task_id, group_id, payload.assigneeId, current_user_id=current_user_id
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BadRequestError as exc:
        raise HTTPException(
            status_code=exc.http_code,
            detail=ErrorDetail(errorCode=exc.error_code, message=exc.message).model_dump(),
        ) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return TaskGroupResponse(**relationship.model_dump())


@group_tasks_router.get(
    "",
    response_model=list[TaskResponse],
    responses={
        404: {"description": "Group not found"},
        403: {"description": "Not authorized"},
    },
)
def list_group_tasks(
    group_id: str,
    current_user_id: str = Depends(verify_firebase_token),
    service: TaskGroupService = Depends(get_task_group_service),
) -> list[TaskResponse]:
    try:
        tasks = service.list_tasks_for_group(group_id, current_user_id=current_user_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return [TaskResponse(**t.model_dump()) for t in tasks]
```

(The old `unassign_task` function and its `@router.delete("/{assignee_id}", ...)` decorator are gone — no other route matches that sub-path, so it now 404s.)

- [ ] **Step 3b: Edit `app/main.py`**

```python
from fastapi import FastAPI

from app.api.v1.groups import router as groups_router
from app.api.v1.task_group import group_tasks_router, router as task_group_router
from app.api.v1.tasks import router as tasks_router
from app.api.v1.user_group import router as user_group_router
from app.api.v1.users import router as users_router

app = FastAPI(title="TaskNest", version="1.0.0")

app.include_router(users_router)
app.include_router(groups_router)
app.include_router(user_group_router)
app.include_router(tasks_router)
app.include_router(task_group_router)
app.include_router(group_tasks_router)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/integration/test_task_group_api.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/v1/task_group.py app/main.py tests/integration/test_task_group_api.py
git commit -m "feat: remove DELETE assignee route, add PATCH reassign and GET group-tasks endpoints"
```

---

## Task 11: Docs — `Arch.md` and `OpenPoints.md`

**Files:**
- Modify: `Arch.md`
- Modify: `OpenPoints.md`

- [ ] **Step 1: Edit `Arch.md`**

In the **Entity relationships** section, update the existing `Task`/`TaskGroupRelationship` bullet and add a new one:

```markdown
- `Task` 0..1—0..1 `Group` via `Task.groupId` (a task's single "home" group,
  set only at creation, immutable thereafter — separate from the
  many-to-many `TaskGroupRelationship` join below). Creating a task with a
  `groupId` requires the creator to already be that group's creator or a
  member (`GroupService.get_group`'s existing check), and automatically
  creates a `TaskGroupRelationship` row with `assigneeId` = the creator,
  inserted directly via `TaskGroupRepository` (bypassing
  `TaskGroupService.assign()`, since a group's own creator can never be a
  `UserGroupRelationship` member row).
- `Task` 0..1—0..N `TaskGroupRelationship` N—0..1 `Group`, with an optional
  `assigneeId` (a `User`) on each join row. A task's creator CAN be its own
  assignee (the prior `ERR_TASKS_005` constraint was retired).
```

In the **API Endpoint Inventory** table, update/add/remove rows:

```markdown
| POST | /api/v1/tasks | Create a task (optional groupId; auto-assigns creator if set) |
...
| POST | /api/v1/groups/{groupId}/tasks/{taskId}/assignee | Assign task to a user within a group (creator only) |
| PATCH | /api/v1/groups/{groupId}/tasks/{taskId}/assignee | Reassign task's assignee within a group (creator or member) |
| GET | /api/v1/groups/{groupId}/tasks | Fetch all tasks belonging to a group (creator or any member) |
```
(remove the `DELETE .../assignee/{assigneeId}` row.)

- [ ] **Step 2: Edit `OpenPoints.md`**

In the **Error codes** table, remove the `ERR_TASKS_005` row and add:
```markdown
| `ERR_TASKS_007` | Requested Task assignee is same as current assignee |
| `ERR_TASKS_008` | Requested Assignee is not part of the Group |
```
Update the note below the table:
```markdown
Note: `ERR_TASKS_004` and `ERR_TASKS_005` are intentionally unused/retired.
`ERR_TASKS_004` was folded into the broadened `ERR_TASKS_002`. `ERR_TASKS_005`
(`TASK_CREATOR_CANNOT_BE_ASSIGNEE`) was retired — task creators can now be
assigned to their own tasks, both via auto-assignment on creation and via
the manual assign endpoint.
```

In the **Auth & authorization** bullet list, update the Tasks line:
```markdown
  - Tasks (read/state/due-date): caller must be the creator or the
    assignee. Task meta update: creator only. Assign: creator only.
    Reassign: creator or any group member (a deliberate divergence from
    assign's creator-only rule). Group-tasks listing: creator or any
    member.
```

In the **Design notes / asymmetries** section, add:
```markdown
- `TaskGroupService.unassign` no longer exists (removed along with its
  `DELETE .../assignee/{assigneeId}` route) — reassignment is now done via
  `PATCH .../assignee` (`reassign`), which requires an existing assignment
  and a different target assignee.
- A `TaskGroupRelationship` row created automatically at task-creation time
  (when `groupId` is set) is indistinguishable from one created via the
  manual `assign`/`reassign` endpoints — there's no "origin" flag.
```

- [ ] **Step 3: Commit**

```bash
git add Arch.md OpenPoints.md
git commit -m "docs: describe groupId, retired ERR_TASKS_005, and the new reassign/group-tasks endpoints"
```

---

## Task 12: Full-suite verification

- [ ] **Step 1: Run the full suite**

```bash
.venv/bin/pytest -v
```
Expected: 100% pass, no skipped/xfail. If any failures surface from interactions between tasks (e.g. a fixture not updated everywhere), fix them in this task rather than reopening earlier tasks' commits — commit the fix separately.

- [ ] **Step 2: Manual smoke test**

```bash
.venv/bin/uvicorn app.main:app --reload
```
Then, using `/docs` or `curl` with a real or stubbed Firebase token (see `app/auth.py` for how `verify_firebase_token` validates), walk through: create user A, create user B, A creates a group, A creates a task with `groupId` set → confirm response has `groupId` and `GET /api/v1/groups/{groupId}/tasks` shows it with `assigneeId=A`; associate B as a member; confirm B can `GET /api/v1/groups/{groupId}/tasks`; confirm a true outsider gets 403 on that same GET; B reassigns the task to themselves via `PATCH .../assignee`; confirm reassigning to the same assignee again returns `ERR_TASKS_007`; confirm reassigning to a non-member returns `ERR_TASKS_008`; confirm `DELETE .../assignee/{assigneeId}` now 404s; confirm `PATCH /api/v1/tasks/{taskId}` no longer needs (or accepts effectively) `updatedBy` in the body and the response's `updatedBy` matches the caller's token identity.

- [ ] **Step 3: Final commit (only if smoke-test fixes were needed)**

```bash
git add -A
git commit -m "fix: address issues found during full-suite/manual verification"
```

---

## Self-review notes (already applied above, recorded per the skill's checklist)

- **Spec coverage**: Ask 1 → Tasks 5, 9. Ask 2 → Tasks 2, 3, 4, 9. Ask 3 → Tasks 8, 10. Ask 4 → Task 4. Ask 5 → Task 10. Ask 6 → Tasks 1, 7, 10. All 6 asks map to at least one task.
- **Type/signature consistency checked**: `TaskService.__init__` 4th arg `group_service` (Task 4) matches every later constructor call site (`app/dependencies.py`, `tests/conftest.py`, `tests/unit/test_task_service.py`). `update_task_meta/update_task_state/update_due_date`'s new `current_user_id`-only signature (Task 5) matches the router call sites written in Task 9. `TaskGroupService.reassign`'s signature (Task 7) matches its router usage in Task 10. `ErrorCode.REASSIGN_ASSIGNEE_UNCHANGED`/`REASSIGN_ASSIGNEE_NOT_GROUP_MEMBER` (Task 1) match their usage in Task 7.
