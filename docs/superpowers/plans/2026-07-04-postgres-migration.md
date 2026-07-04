# PostgreSQL Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace TaskNest's in-memory dict repositories entirely with PostgreSQL 17-backed repositories (SQLAlchemy + psycopg3 + Alembic), rewriting every existing test to run against real Postgres — no in-memory fallback left anywhere.

**Architecture:** Each of the 5 existing repository files (`app/repositories/{user,task,group,user_group,task_group}_repository.py`) gets its `InMemory*Repository` class replaced by a same-named, Postgres-backed class (`UserRepository`, `TaskRepository`, `GroupRepository`, `UserGroupRepository`, `TaskGroupRepository`) that implements `BaseRepository[T]` plus that entity's extra query methods, mapping Pydantic domain models ↔ SQLAlchemy ORM rows via an injected `Session`. Services keep depending on the same types they already do (`BaseRepository[T]` for `User`/`Task`; the concrete `Group`/`UserGroup`/`TaskGroup` repository classes for the other three, per `Arch.md`'s existing documented exception) — only the underlying implementation changes. **Sequencing note:** to avoid breaking the whole test suite mid-migration (many existing test fixtures build all 5 repositories together), Tasks 3-7 *add* each new Postgres-backed class alongside its still-present in-memory sibling (existing tests keep passing throughout), and Task 8 is a single cutover that deletes all 5 in-memory classes and rewrites every consuming test/fixture/DI-wiring file in one atomic step, verified by a full green run.

**Tech Stack:** SQLAlchemy 2.0 (sync `Session`, declarative models), psycopg3 (`psycopg[binary]`), Alembic, PostgreSQL 17 (local via Homebrew, already running as macOS user `ranjith`, no password).

## Global Constraints

- Database name: `tasks_net_db` (test database: `tasks_net_db_test`), per `ASK.md`.
- Table names exactly: `users`, `groups`, `user_groups`, `tasks`, `group_tasks`, per `ASK.md`.
- Add PK + FK constraints and indexes where applicable, per `ASK.md`.
- No `InMemory*Repository` class survives past Task 8 — the entire codebase and test suite run against real Postgres.
- `VARCHAR`/`TEXT` (not native `UUID`) for all PK/FK columns; `User.name` stored as a single `JSON` column; Alembic (not `create_all()`) for schema management; no docker-compose Postgres service (target local Homebrew Postgres only) — all confirmed with the user.
- `TaskGroupRelationship`/`group_tasks.assignee_id` must stay nullable and only ever be `UPDATE`d to `NULL` on unassign — never row-deleted (existing, documented behavior in `OpenPoints.md`).
- No lint/format tooling is configured in this repo — don't add any.

---

## Task 1: Dependencies, SQLAlchemy scaffolding, Alembic init, shared DB test fixtures

**Files:**
- Modify: `requirements.txt`
- Create: `app/db/__init__.py`, `app/db/base.py`, `app/db/session.py`
- Create: `.env.example`
- Create (via `alembic init`): `alembic.ini`, `migrations/env.py`, `migrations/script.py.mako`, `migrations/versions/`
- Modify: `tests/conftest.py` (add `db_session`/`_schema` fixtures only — the existing `client` fixture is untouched until Task 8)

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `app.db.base.Base`; `app.db.session.get_db_session() -> Generator[Session, None, None]`; a `db_session` pytest fixture (function-scoped, transaction+savepoint rollback) usable from any test under `tests/` — Tasks 3-8 all consume it.

- [ ] **Step 1: Create the two local databases**

Run:
```bash
/opt/homebrew/opt/postgresql@17/bin/createdb tasks_net_db
/opt/homebrew/opt/postgresql@17/bin/createdb tasks_net_db_test
```
Expected: no output. Verify: `/opt/homebrew/opt/postgresql@17/bin/psql -l | grep tasks_net_db` shows both.

- [ ] **Step 2: Add the new dependencies**

In `requirements.txt`, change:
```
fastapi==0.115.6
uvicorn[standard]==0.34.0
pydantic==2.10.4
```
to:
```
fastapi==0.115.6
uvicorn[standard]==0.34.0
pydantic==2.10.4
sqlalchemy==2.0.36
psycopg[binary]==3.2.3
alembic==1.14.0
```

- [ ] **Step 3: Install and verify**

Run: `.venv/bin/pip install -r requirements.txt`
Run: `.venv/bin/python -c "import sqlalchemy, psycopg, alembic; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Create the declarative base and session module**

Create `app/db/__init__.py` (empty file).

Create `app/db/base.py`:
```python
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

Create `app/db/session.py`:
```python
import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://ranjith@localhost:5432/tasks_net_db"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

- [ ] **Step 5: Verify the engine connects**

Run: `.venv/bin/python -c "from app.db.session import engine; engine.connect(); print('connected')"`
Expected: `connected`

- [ ] **Step 6: Document the connection env vars**

Create `.env.example`:
```
DATABASE_URL=postgresql+psycopg://ranjith@localhost:5432/tasks_net_db
TEST_DATABASE_URL=postgresql+psycopg://ranjith@localhost:5432/tasks_net_db_test
```

- [ ] **Step 7: Initialize Alembic**

Run: `.venv/bin/alembic init migrations`
Expected: creates `alembic.ini`, `migrations/env.py`, `migrations/script.py.mako`, `migrations/README`, `migrations/versions/` (empty).

- [ ] **Step 8: Wire Alembic to read `DATABASE_URL` from the environment**

In `migrations/env.py`, immediately after `config = context.config`, add:
```python
import os

config.set_main_option(
    "sqlalchemy.url",
    os.environ.get("DATABASE_URL", "postgresql+psycopg://ranjith@localhost:5432/tasks_net_db"),
)
```
Then find the generated line `target_metadata = None` and replace it with:
```python
from app.db.base import Base

target_metadata = Base.metadata
```
(Leave the rest of the generated file — `run_migrations_offline`/`run_migrations_online` and their boilerplate — untouched.)

- [ ] **Step 9: Verify Alembic can connect**

Run: `.venv/bin/alembic current`
Expected: no error.

- [ ] **Step 10: Add the shared DB test fixtures**

In `tests/conftest.py`, add these imports and fixtures ABOVE the existing `client` fixture (don't touch the `client` fixture itself yet — that happens in Task 8):
```python
import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.db import orm_models  # noqa: F401
from app.db.base import Base

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://ranjith@localhost:5432/tasks_net_db_test"
)
engine = create_engine(TEST_DATABASE_URL)


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def db_session():
    connection = engine.connect()
    outer_txn = connection.begin()
    session_factory = sessionmaker(bind=connection)
    session = session_factory()
    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess, trans):
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    yield session

    session.close()
    outer_txn.rollback()
    connection.close()
```
Note: `from app.db import orm_models` will fail until Task 2 creates that module — that's expected; this step's own verification (below) only checks the file parses and existing tests still pass, not that `db_session` itself works yet (nothing uses it yet).

- [ ] **Step 11: Verify nothing existing broke**

Run: `.venv/bin/pytest tests/unit tests/integration -v`
Expected: FAIL at collection with `ModuleNotFoundError: No module named 'app.db.orm_models'` (from the new import in `tests/conftest.py`) — this is expected and resolved by Task 2. If you want a clean green checkpoint here instead, comment out the `from app.db import orm_models` line and the `_schema`/`db_session` fixture bodies until Task 2, then uncomment in Task 2 Step 2. Either approach is fine; the plan assumes the commented-out approach for a clean commit boundary — see Task 2 Step 2.

Actually: comment out the new import and fixtures added in Step 10 for now (wrap in place, don't delete), so this task's commit leaves the suite green:
```python
# from app.db import orm_models  # noqa: F401  -- uncommented in Task 2

# TEST_DATABASE_URL = os.environ.get(
#     "TEST_DATABASE_URL", "postgresql+psycopg://ranjith@localhost:5432/tasks_net_db_test"
# )
# engine = create_engine(TEST_DATABASE_URL)


# @pytest.fixture(scope="session", autouse=True)
# def _schema():
#     Base.metadata.create_all(engine)
#     yield
#     Base.metadata.drop_all(engine)


# @pytest.fixture
# def db_session():
#     ...
```
Run: `.venv/bin/pytest tests/unit tests/integration -v`
Expected: PASS (all existing tests, unaffected).

- [ ] **Step 12: Commit**

```bash
git add requirements.txt app/db/__init__.py app/db/base.py app/db/session.py .env.example alembic.ini migrations/ tests/conftest.py
git commit -m "chore: add SQLAlchemy/psycopg/alembic scaffolding for Postgres migration"
```

---

## Task 2: SQLAlchemy ORM models + initial migration

**Files:**
- Create: `app/db/orm_models.py`
- Modify: `migrations/env.py`
- Modify: `tests/conftest.py` (uncomment Task 1's Step 11 block)
- Create (via `alembic revision --autogenerate`): `migrations/versions/<hash>_create_initial_tables.py`

**Interfaces:**
- Consumes: `app.db.base.Base` (Task 1).
- Produces: `UserRow`, `GroupRow`, `UserGroupRow`, `TaskRow`, `GroupTaskRow` ORM classes — Tasks 3-8 map domain models to/from these by exact column name.

- [ ] **Step 1: Write the ORM models**

Create `app/db/orm_models.py`:
```python
import uuid

from sqlalchemy import Column, DateTime, Enum, ForeignKey, JSON, String, UniqueConstraint

from app.db.base import Base
from app.models.enums import GroupStatus, TaskState, UserStatus


def _enum_column(enum_cls, constraint_name, default):
    return Column(
        Enum(
            enum_cls,
            values_callable=lambda e: [m.value for m in e],
            native_enum=False,
            name=constraint_name,
            length=20,
        ),
        nullable=False,
        server_default=default.value,
    )


class UserRow(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(JSON, nullable=False)
    phone_num = Column(String(20), nullable=True)
    email_id = Column(String(255), nullable=True)
    user_status = _enum_column(UserStatus, "ck_users_user_status", UserStatus.ACTIVE)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)


class GroupRow(Base):
    __tablename__ = "groups"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    group_name = Column(String(200), nullable=False)
    group_desc = Column(String(1000), nullable=True)
    group_category = Column(String(100), nullable=False)
    group_status = _enum_column(GroupStatus, "ck_groups_group_status", GroupStatus.ACTIVE)
    group_icon_url = Column(String(500), nullable=True)
    group_creater_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)


class UserGroupRow(Base):
    __tablename__ = "user_groups"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    group_id = Column(String(36), ForeignKey("groups.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    # Python attribute renamed to avoid clashing with sqlalchemy.orm.relationship;
    # the actual database column name is still exactly "relationship".
    relationship_label = Column("relationship", String(100), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "group_id", name="uq_user_groups_user_id_group_id"),
    )


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


class GroupTaskRow(Base):
    __tablename__ = "group_tasks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=False, index=True)
    group_id = Column(String(36), ForeignKey("groups.id"), nullable=False, index=True)
    assignee_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)

    __table_args__ = (
        UniqueConstraint("task_id", "group_id", name="uq_group_tasks_task_id_group_id"),
    )
```

- [ ] **Step 2: Uncomment the DB test fixtures added in Task 1**

In `tests/conftest.py`, uncomment the block added in Task 1 Step 10/11 (the `orm_models` import, `TEST_DATABASE_URL`, `engine`, `_schema`, and `db_session` fixture).

- [ ] **Step 3: Register the models with Alembic's autogenerate**

In `migrations/env.py`, change:
```python
from app.db.base import Base

target_metadata = Base.metadata
```
to:
```python
from app.db.base import Base
from app.db import orm_models  # noqa: F401 — registers all 5 tables on Base.metadata

target_metadata = Base.metadata
```

- [ ] **Step 4: Generate the migration**

Run: `.venv/bin/alembic revision --autogenerate -m "create initial tables"`
Expected: creates one new file under `migrations/versions/`.

- [ ] **Step 5: Review the generated migration against this checklist**

Confirm the file contains:
- `create_table` for `users`, `groups`, `user_groups`, `tasks`, `group_tasks`.
- PK on each table's `id`.
- FKs: `groups.group_creater_id`→`users.id`; `user_groups.group_id`→`groups.id`, `user_groups.user_id`→`users.id`; `tasks.created_by`→`users.id`, `tasks.updated_by`→`users.id`; `group_tasks.task_id`→`tasks.id`, `group_tasks.group_id`→`groups.id`, `group_tasks.assignee_id`→`users.id`.
- Indexes on every FK column listed above.
- Unique constraints: `uq_user_groups_user_id_group_id`, `uq_group_tasks_task_id_group_id`.
- CHECK constraints: `ck_users_user_status`, `ck_groups_group_status`, `ck_tasks_task_state`.

Fix the generated file directly if anything is missing.

- [ ] **Step 6: Apply the migration**

Run: `.venv/bin/alembic upgrade head`
Expected: no errors.

- [ ] **Step 7: Verify the schema**

Run: `/opt/homebrew/opt/postgresql@17/bin/psql tasks_net_db -c "\dt"`
Expected: lists all 5 tables plus `alembic_version`.

- [ ] **Step 8: Run the existing suite to confirm nothing broke**

Run: `.venv/bin/pytest tests/unit tests/integration -v`
Expected: PASS (the uncommented `db_session`/`_schema` fixtures now import successfully but aren't used by any existing test yet, so behavior is unchanged).

- [ ] **Step 9: Commit**

```bash
git add app/db/orm_models.py migrations/ tests/conftest.py
git commit -m "feat: add SQLAlchemy ORM models and initial Postgres migration"
```

---

## Task 3: User repository (Postgres-backed, added alongside in-memory)

**Files:**
- Modify: `app/repositories/user_repository.py` (add `UserRepository`, keep `InMemoryUserRepository` for now)
- Create: `tests/repositories/__init__.py`, `tests/repositories/test_user_repository.py`

**Interfaces:**
- Consumes: `app.db.orm_models.UserRow` (Task 2), the `db_session` fixture (Task 1).
- Produces: `UserRepository(session: Session)` implementing `add`, `get`, `update`, `list_all` for `User`. Task 4-7's tests reuse the `_make_user_row(db_session, user_id)` helper pattern shown here.

- [ ] **Step 1: Write the failing test**

Create `tests/repositories/__init__.py` (empty file).

Create `tests/repositories/test_user_repository.py`:
```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/repositories/test_user_repository.py -v`
Expected: FAIL with `ImportError: cannot import name 'UserRepository' from 'app.repositories.user_repository'`.

- [ ] **Step 3: Add the repository (keep the in-memory one for now)**

In `app/repositories/user_repository.py`, ADD this class at the end of the file (leave the existing `InMemoryUserRepository` class untouched above it):
```python
from sqlalchemy.orm import Session

from app.db.orm_models import UserRow


class UserRepository(BaseRepository[User]):
    def __init__(self, session: Session):
        self._session = session

    def add(self, entity: User) -> User:
        row = UserRow(
            id=entity.userId,
            name={"firstName": entity.name.firstName, "lastName": entity.name.lastName},
            phone_num=entity.phoneNum,
            email_id=entity.emailId,
            user_status=entity.userStatus,
            created_at=entity.createdAt,
            updated_at=entity.updatedAt,
        )
        self._session.add(row)
        self._session.flush()
        return entity

    def get(self, entity_id: str) -> Optional[User]:
        row = self._session.get(UserRow, entity_id)
        return self._to_domain(row) if row is not None else None

    def update(self, entity: User) -> User:
        row = self._session.get(UserRow, entity.userId)
        row.name = {"firstName": entity.name.firstName, "lastName": entity.name.lastName}
        row.phone_num = entity.phoneNum
        row.email_id = entity.emailId
        row.user_status = entity.userStatus
        row.updated_at = entity.updatedAt
        self._session.flush()
        return entity

    def list_all(self) -> list[User]:
        return [self._to_domain(row) for row in self._session.query(UserRow).all()]

    @staticmethod
    def _to_domain(row: UserRow) -> User:
        return User(
            userId=row.id,
            name=Name(firstName=row.name["firstName"], lastName=row.name["lastName"]),
            phoneNum=row.phone_num,
            emailId=row.email_id,
            userStatus=row.user_status,
            createdAt=row.created_at,
            updatedAt=row.updated_at,
        )
```
(`BaseRepository`, `User`, `Name`, `Optional` are already imported at the top of this file for `InMemoryUserRepository` — only the two new imports shown above, `Session` and `UserRow`, need adding.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/repositories/test_user_repository.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Confirm nothing existing broke**

Run: `.venv/bin/pytest tests/unit tests/integration -v`
Expected: PASS (still using `InMemoryUserRepository`, untouched).

- [ ] **Step 6: Commit**

```bash
git add app/repositories/user_repository.py tests/repositories/
git commit -m "feat: add Postgres-backed user repository"
```

---

## Task 4: Task repository (Postgres-backed, added alongside in-memory)

**Files:**
- Modify: `app/repositories/task_repository.py`
- Create: `tests/repositories/test_task_repository.py`

**Interfaces:**
- Consumes: `app.db.orm_models.TaskRow`/`UserRow` (Task 2), `db_session` (Task 1).
- Produces: `TaskRepository(session: Session)` implementing `add`, `get`, `update`, `list_all` for `Task`.

- [ ] **Step 1: Write the failing test**

Create `tests/repositories/test_task_repository.py`:
```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/repositories/test_task_repository.py -v`
Expected: FAIL with `ImportError: cannot import name 'TaskRepository' from 'app.repositories.task_repository'`.

- [ ] **Step 3: Add the repository (keep the in-memory one for now)**

In `app/repositories/task_repository.py`, ADD at the end of the file:
```python
from sqlalchemy.orm import Session

from app.db.orm_models import TaskRow


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
        )
        self._session.add(row)
        self._session.flush()
        return entity

    def get(self, entity_id: str) -> Optional[Task]:
        row = self._session.get(TaskRow, entity_id)
        return self._to_domain(row) if row is not None else None

    def update(self, entity: Task) -> Task:
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
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/repositories/test_task_repository.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Confirm nothing existing broke**

Run: `.venv/bin/pytest tests/unit tests/integration -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/repositories/task_repository.py tests/repositories/test_task_repository.py
git commit -m "feat: add Postgres-backed task repository"
```

---

## Task 5: Group repository (Postgres-backed, added alongside in-memory)

**Files:**
- Modify: `app/repositories/group_repository.py`
- Create: `tests/repositories/test_group_repository.py`

**Interfaces:**
- Consumes: `app.db.orm_models.GroupRow`/`UserRow` (Task 2), `db_session` (Task 1).
- Produces: `GroupRepository(session: Session)` implementing `add`, `get`, `update`, `list_all`, `list_by_creator` for `Group`. Task 8 changes `GroupService`'s constructor to depend on this instead of `InMemoryGroupRepository`.

- [ ] **Step 1: Write the failing test**

Create `tests/repositories/test_group_repository.py`:
```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/repositories/test_group_repository.py -v`
Expected: FAIL with `ImportError: cannot import name 'GroupRepository' from 'app.repositories.group_repository'`.

- [ ] **Step 3: Add the repository (keep the in-memory one for now)**

In `app/repositories/group_repository.py`, ADD at the end of the file:
```python
from sqlalchemy.orm import Session

from app.db.orm_models import GroupRow


class GroupRepository(BaseRepository[Group]):
    def __init__(self, session: Session):
        self._session = session

    def add(self, entity: Group) -> Group:
        row = GroupRow(
            id=entity.groupId,
            group_name=entity.groupName,
            group_desc=entity.groupDesc,
            group_category=entity.groupCategory,
            group_status=entity.groupStatus,
            group_icon_url=entity.groupIconUrl,
            group_creater_id=entity.groupCreaterId,
            created_at=entity.createdAt,
            updated_at=entity.updatedAt,
        )
        self._session.add(row)
        self._session.flush()
        return entity

    def get(self, entity_id: str) -> Optional[Group]:
        row = self._session.get(GroupRow, entity_id)
        return self._to_domain(row) if row is not None else None

    def update(self, entity: Group) -> Group:
        row = self._session.get(GroupRow, entity.groupId)
        row.group_name = entity.groupName
        row.group_desc = entity.groupDesc
        row.group_status = entity.groupStatus
        row.group_icon_url = entity.groupIconUrl
        row.updated_at = entity.updatedAt
        self._session.flush()
        return entity

    def list_all(self) -> list[Group]:
        return [self._to_domain(row) for row in self._session.query(GroupRow).all()]

    def list_by_creator(self, creater_id: str) -> list[Group]:
        rows = self._session.query(GroupRow).filter(GroupRow.group_creater_id == creater_id).all()
        return [self._to_domain(row) for row in rows]

    @staticmethod
    def _to_domain(row: GroupRow) -> Group:
        return Group(
            groupId=row.id,
            groupName=row.group_name,
            groupDesc=row.group_desc,
            groupCategory=row.group_category,
            groupStatus=row.group_status,
            groupIconUrl=row.group_icon_url,
            groupCreaterId=row.group_creater_id,
            createdAt=row.created_at,
            updatedAt=row.updated_at,
        )
```
(This new `GroupRepository` name will collide with nothing today since the in-memory class is named `InMemoryGroupRepository` — both classes coexist in this file until Task 8.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/repositories/test_group_repository.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Confirm nothing existing broke**

Run: `.venv/bin/pytest tests/unit tests/integration -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/repositories/group_repository.py tests/repositories/test_group_repository.py
git commit -m "feat: add Postgres-backed group repository"
```

---

## Task 6: UserGroup repository (Postgres-backed, added alongside in-memory)

**Files:**
- Modify: `app/repositories/user_group_repository.py`
- Create: `tests/repositories/test_user_group_repository.py`

**Interfaces:**
- Consumes: `app.db.orm_models.UserGroupRow`/`GroupRow`/`UserRow` (Task 2), `db_session` (Task 1).
- Produces: `UserGroupRepository(session: Session)` implementing `add`, `get`, `update`, `list_all`, `find_by_user_and_group`, `list_by_group`, `delete`. Task 8 changes `UserGroupService`'s constructor to depend on this instead of `InMemoryUserGroupRepository`.

- [ ] **Step 1: Write the failing tests**

Create `tests/repositories/test_user_group_repository.py`:
```python
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

    repo.add(_make_relationship())
    with pytest.raises(IntegrityError):
        db_session.flush()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/repositories/test_user_group_repository.py -v`
Expected: FAIL with `ImportError: cannot import name 'UserGroupRepository' from 'app.repositories.user_group_repository'`.

- [ ] **Step 3: Add the repository (keep the in-memory one for now)**

In `app/repositories/user_group_repository.py`, ADD at the end of the file:
```python
from sqlalchemy.orm import Session

from app.db.orm_models import UserGroupRow


class UserGroupRepository(BaseRepository[UserGroupRelationship]):
    def __init__(self, session: Session):
        self._session = session

    def add(self, entity: UserGroupRelationship) -> UserGroupRelationship:
        row = UserGroupRow(
            id=entity.uuid,
            group_id=entity.groupId,
            user_id=entity.userId,
            relationship_label=entity.relationship,
        )
        self._session.add(row)
        self._session.flush()
        return entity

    def get(self, entity_id: str) -> Optional[UserGroupRelationship]:
        row = self._session.get(UserGroupRow, entity_id)
        return self._to_domain(row) if row is not None else None

    def update(self, entity: UserGroupRelationship) -> UserGroupRelationship:
        row = self._session.get(UserGroupRow, entity.uuid)
        row.relationship_label = entity.relationship
        self._session.flush()
        return entity

    def list_all(self) -> list[UserGroupRelationship]:
        return [self._to_domain(row) for row in self._session.query(UserGroupRow).all()]

    def find_by_user_and_group(
        self, user_id: str, group_id: str
    ) -> Optional[UserGroupRelationship]:
        row = (
            self._session.query(UserGroupRow)
            .filter(UserGroupRow.user_id == user_id, UserGroupRow.group_id == group_id)
            .first()
        )
        return self._to_domain(row) if row is not None else None

    def list_by_group(self, group_id: str) -> list[UserGroupRelationship]:
        rows = self._session.query(UserGroupRow).filter(UserGroupRow.group_id == group_id).all()
        return [self._to_domain(row) for row in rows]

    def delete(self, entity_id: str) -> None:
        row = self._session.get(UserGroupRow, entity_id)
        if row is not None:
            self._session.delete(row)
            self._session.flush()

    @staticmethod
    def _to_domain(row: UserGroupRow) -> UserGroupRelationship:
        return UserGroupRelationship(
            uuid=row.id,
            groupId=row.group_id,
            userId=row.user_id,
            relationship=row.relationship_label,
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/repositories/test_user_group_repository.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Confirm nothing existing broke**

Run: `.venv/bin/pytest tests/unit tests/integration -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/repositories/user_group_repository.py tests/repositories/test_user_group_repository.py
git commit -m "feat: add Postgres-backed user-group repository"
```

---

## Task 7: TaskGroup repository (Postgres-backed, added alongside in-memory)

**Files:**
- Modify: `app/repositories/task_group_repository.py`
- Create: `tests/repositories/test_task_group_repository.py`

**Interfaces:**
- Consumes: `app.db.orm_models.GroupTaskRow`/`TaskRow`/`GroupRow`/`UserRow` (Task 2), `db_session` (Task 1).
- Produces: `TaskGroupRepository(session: Session)` implementing `add`, `get`, `update`, `list_all`, `find_by_task_and_group`. Task 8 changes `TaskGroupService`'s constructor to depend on this instead of `InMemoryTaskGroupRepository`.

- [ ] **Step 1: Write the failing tests**

Create `tests/repositories/test_task_group_repository.py`:
```python
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

    repo.add(_make_relationship())
    with pytest.raises(IntegrityError):
        db_session.flush()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/repositories/test_task_group_repository.py -v`
Expected: FAIL with `ImportError: cannot import name 'TaskGroupRepository' from 'app.repositories.task_group_repository'`.

- [ ] **Step 3: Add the repository (keep the in-memory one for now)**

In `app/repositories/task_group_repository.py`, ADD at the end of the file:
```python
from sqlalchemy.orm import Session

from app.db.orm_models import GroupTaskRow


class TaskGroupRepository(BaseRepository[TaskGroupRelationship]):
    def __init__(self, session: Session):
        self._session = session

    def add(self, entity: TaskGroupRelationship) -> TaskGroupRelationship:
        row = GroupTaskRow(
            id=entity.uuid,
            task_id=entity.taskId,
            group_id=entity.groupId,
            assignee_id=entity.assigneeId,
        )
        self._session.add(row)
        self._session.flush()
        return entity

    def get(self, entity_id: str) -> Optional[TaskGroupRelationship]:
        row = self._session.get(GroupTaskRow, entity_id)
        return self._to_domain(row) if row is not None else None

    def update(self, entity: TaskGroupRelationship) -> TaskGroupRelationship:
        row = self._session.get(GroupTaskRow, entity.uuid)
        row.assignee_id = entity.assigneeId
        self._session.flush()
        return entity

    def list_all(self) -> list[TaskGroupRelationship]:
        return [self._to_domain(row) for row in self._session.query(GroupTaskRow).all()]

    def find_by_task_and_group(
        self, task_id: str, group_id: str
    ) -> Optional[TaskGroupRelationship]:
        row = (
            self._session.query(GroupTaskRow)
            .filter(GroupTaskRow.task_id == task_id, GroupTaskRow.group_id == group_id)
            .first()
        )
        return self._to_domain(row) if row is not None else None

    @staticmethod
    def _to_domain(row: GroupTaskRow) -> TaskGroupRelationship:
        return TaskGroupRelationship(
            uuid=row.id,
            taskId=row.task_id,
            groupId=row.group_id,
            assigneeId=row.assignee_id,
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/repositories/test_task_group_repository.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Confirm nothing existing broke**

Run: `.venv/bin/pytest tests/unit tests/integration -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/repositories/task_group_repository.py tests/repositories/test_task_group_repository.py
git commit -m "feat: add Postgres-backed task-group repository"
```

---

## Task 8: Cutover — delete in-memory repositories, rewire every consumer

**Files:**
- Modify: `app/repositories/{user,task,group,user_group,task_group}_repository.py` (delete `InMemory*` classes)
- Modify: `app/services/group_service.py`, `app/services/user_group_service.py`, `app/services/task_group_service.py`
- Modify: `tests/unit/test_user_service.py`, `test_task_service.py`, `test_group_service.py`, `test_user_group_service.py`, `test_task_group_service.py`
- Modify: `tests/conftest.py` (rewrite the `client` fixture)
- Modify: `app/dependencies.py`

**Interfaces:**
- Consumes: `UserRepository`/`TaskRepository`/`GroupRepository`/`UserGroupRepository`/`TaskGroupRepository` (Tasks 3-7), `app.db.session.get_db_session` (Task 1).
- Produces: the app's real runtime composition backed entirely by PostgreSQL, with zero in-memory code remaining. No new interfaces for later tasks.

- [ ] **Step 1: Delete the 5 in-memory repository classes**

In each of these files, delete the `InMemory*Repository` class body entirely (keep the new Postgres-backed class already added by Tasks 3-7, and trim now-unused imports — e.g. `InMemoryUserRepository` no longer exists, so nothing else in the file should reference it):
- `app/repositories/user_repository.py`: delete `class InMemoryUserRepository(BaseRepository[User]): ...`.
- `app/repositories/task_repository.py`: delete `class InMemoryTaskRepository(BaseRepository[Task]): ...`.
- `app/repositories/group_repository.py`: delete `class InMemoryGroupRepository(BaseRepository[Group]): ...`.
- `app/repositories/user_group_repository.py`: delete `class InMemoryUserGroupRepository(BaseRepository[UserGroupRelationship]): ...`.
- `app/repositories/task_group_repository.py`: delete `class InMemoryTaskGroupRepository(BaseRepository[TaskGroupRelationship]): ...`.

- [ ] **Step 2: Update `GroupService`'s import**

In `app/services/group_service.py`, change:
```python
from app.repositories.group_repository import InMemoryGroupRepository
```
to:
```python
from app.repositories.group_repository import GroupRepository
```
and change:
```python
    def __init__(self, repository: InMemoryGroupRepository, user_service: UserService):
```
to:
```python
    def __init__(self, repository: GroupRepository, user_service: UserService):
```

- [ ] **Step 3: Update `UserGroupService`'s import**

In `app/services/user_group_service.py`, change:
```python
from app.repositories.user_group_repository import InMemoryUserGroupRepository
```
to:
```python
from app.repositories.user_group_repository import UserGroupRepository
```
and change:
```python
    def __init__(
        self,
        repository: InMemoryUserGroupRepository,
        user_service: UserService,
        group_service: GroupService,
    ):
```
to:
```python
    def __init__(
        self,
        repository: UserGroupRepository,
        user_service: UserService,
        group_service: GroupService,
    ):
```

- [ ] **Step 4: Update `TaskGroupService`'s import**

In `app/services/task_group_service.py`, change:
```python
from app.repositories.task_group_repository import InMemoryTaskGroupRepository
```
to:
```python
from app.repositories.task_group_repository import TaskGroupRepository
```
and change:
```python
    def __init__(
        self,
        repository: InMemoryTaskGroupRepository,
        task_service: TaskService,
        group_service: GroupService,
        user_service: UserService,
        user_group_service: UserGroupService,
    ):
```
to:
```python
    def __init__(
        self,
        repository: TaskGroupRepository,
        task_service: TaskService,
        group_service: GroupService,
        user_service: UserService,
        user_group_service: UserGroupService,
    ):
```

- [ ] **Step 5: Rewrite `tests/unit/test_user_service.py`'s fixture**

Change:
```python
from app.repositories.user_repository import InMemoryUserRepository
from app.services.user_service import UserService


@pytest.fixture
def service() -> UserService:
    return UserService(InMemoryUserRepository())
```
to:
```python
from app.repositories.user_repository import UserRepository
from app.services.user_service import UserService


@pytest.fixture
def service(db_session) -> UserService:
    return UserService(UserRepository(db_session))
```

- [ ] **Step 6: Rewrite `tests/unit/test_task_service.py`'s fixtures**

Change:
```python
from app.repositories.task_repository import InMemoryTaskRepository
from app.repositories.user_repository import InMemoryUserRepository
from app.services.task_service import TaskService
from app.services.user_service import UserService


@pytest.fixture
def user_service() -> UserService:
    return UserService(InMemoryUserRepository())


@pytest.fixture
def task_service(user_service: UserService) -> TaskService:
    return TaskService(InMemoryTaskRepository(), user_service)
```
to:
```python
from app.repositories.task_repository import TaskRepository
from app.repositories.user_repository import UserRepository
from app.services.task_service import TaskService
from app.services.user_service import UserService


@pytest.fixture
def user_service(db_session) -> UserService:
    return UserService(UserRepository(db_session))


@pytest.fixture
def task_service(db_session, user_service: UserService) -> TaskService:
    return TaskService(TaskRepository(db_session), user_service)
```

- [ ] **Step 7: Rewrite `tests/unit/test_group_service.py`'s fixtures**

Change:
```python
from app.repositories.group_repository import InMemoryGroupRepository
from app.repositories.user_repository import InMemoryUserRepository
from app.services.group_service import GroupService
from app.services.user_service import UserService


@pytest.fixture
def user_service() -> UserService:
    return UserService(InMemoryUserRepository())


@pytest.fixture
def group_service(user_service: UserService) -> GroupService:
    return GroupService(InMemoryGroupRepository(), user_service)
```
to:
```python
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
```

- [ ] **Step 8: Rewrite `tests/unit/test_user_group_service.py`'s fixtures**

Change:
```python
from app.repositories.group_repository import InMemoryGroupRepository
from app.repositories.user_group_repository import InMemoryUserGroupRepository
from app.repositories.user_repository import InMemoryUserRepository
from app.services.group_service import GroupService
from app.services.user_group_service import UserGroupService
from app.services.user_service import UserService


@pytest.fixture
def user_service() -> UserService:
    return UserService(InMemoryUserRepository())


@pytest.fixture
def group_service(user_service: UserService) -> GroupService:
    return GroupService(InMemoryGroupRepository(), user_service)


@pytest.fixture
def user_group_service(user_service: UserService, group_service: GroupService) -> UserGroupService:
    return UserGroupService(InMemoryUserGroupRepository(), user_service, group_service)
```
to:
```python
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
```

- [ ] **Step 9: Rewrite `tests/unit/test_task_group_service.py`'s fixtures**

Change:
```python
from app.repositories.group_repository import InMemoryGroupRepository
from app.repositories.task_group_repository import InMemoryTaskGroupRepository
from app.repositories.task_repository import InMemoryTaskRepository
from app.repositories.user_group_repository import InMemoryUserGroupRepository
from app.repositories.user_repository import InMemoryUserRepository
from app.services.group_service import GroupService
from app.services.task_group_service import TaskGroupService
from app.services.task_service import TaskService
from app.services.user_group_service import UserGroupService
from app.services.user_service import UserService


@pytest.fixture
def user_service() -> UserService:
    return UserService(InMemoryUserRepository())


@pytest.fixture
def group_service(user_service: UserService) -> GroupService:
    return GroupService(InMemoryGroupRepository(), user_service)


@pytest.fixture
def task_service(user_service: UserService) -> TaskService:
    return TaskService(InMemoryTaskRepository(), user_service)


@pytest.fixture
def user_group_service(user_service: UserService, group_service: GroupService) -> UserGroupService:
    return UserGroupService(InMemoryUserGroupRepository(), user_service, group_service)


@pytest.fixture
def task_group_service(
    task_service: TaskService,
    group_service: GroupService,
    user_service: UserService,
    user_group_service: UserGroupService,
) -> TaskGroupService:
    return TaskGroupService(
        InMemoryTaskGroupRepository(), task_service, group_service, user_service, user_group_service
    )
```
to:
```python
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
    return GroupService(GroupRepository(db_session), user_service)


@pytest.fixture
def task_service(db_session, user_service: UserService) -> TaskService:
    return TaskService(TaskRepository(db_session), user_service)


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
```

- [ ] **Step 10: Rewrite `tests/conftest.py`'s `client` fixture**

Change:
```python
from app.repositories.group_repository import InMemoryGroupRepository
from app.repositories.task_group_repository import InMemoryTaskGroupRepository
from app.repositories.task_repository import InMemoryTaskRepository
from app.repositories.user_group_repository import InMemoryUserGroupRepository
from app.repositories.user_repository import InMemoryUserRepository
```
to:
```python
from app.repositories.group_repository import GroupRepository
from app.repositories.task_group_repository import TaskGroupRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.user_group_repository import UserGroupRepository
from app.repositories.user_repository import UserRepository
```
and change:
```python
@pytest.fixture
def client():
    user_repo = InMemoryUserRepository()
    group_repo = InMemoryGroupRepository()
    user_group_repo = InMemoryUserGroupRepository()
    task_repo = InMemoryTaskRepository()
    task_group_repo = InMemoryTaskGroupRepository()
```
to:
```python
@pytest.fixture
def client(db_session):
    user_repo = UserRepository(db_session)
    group_repo = GroupRepository(db_session)
    user_group_repo = UserGroupRepository(db_session)
    task_repo = TaskRepository(db_session)
    task_group_repo = TaskGroupRepository(db_session)
```
(The rest of the `client` fixture body — building services and wiring `app.dependency_overrides` — is unchanged.)

- [ ] **Step 11: Rewrite `app/dependencies.py`**

Replace the entire file with:
```python
from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db_session
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


def get_user_repository(session: Session = Depends(get_db_session)) -> UserRepository:
    return UserRepository(session)


def get_user_service(repository: UserRepository = Depends(get_user_repository)) -> UserService:
    return UserService(repository)


def get_group_repository(session: Session = Depends(get_db_session)) -> GroupRepository:
    return GroupRepository(session)


def get_group_service(
    repository: GroupRepository = Depends(get_group_repository),
    user_service: UserService = Depends(get_user_service),
) -> GroupService:
    return GroupService(repository, user_service)


def get_user_group_repository(session: Session = Depends(get_db_session)) -> UserGroupRepository:
    return UserGroupRepository(session)


def get_user_group_service(
    repository: UserGroupRepository = Depends(get_user_group_repository),
    user_service: UserService = Depends(get_user_service),
    group_service: GroupService = Depends(get_group_service),
) -> UserGroupService:
    return UserGroupService(repository, user_service, group_service)


def get_task_repository(session: Session = Depends(get_db_session)) -> TaskRepository:
    return TaskRepository(session)


def get_task_service(
    repository: TaskRepository = Depends(get_task_repository),
    user_service: UserService = Depends(get_user_service),
) -> TaskService:
    return TaskService(repository, user_service)


def get_task_group_repository(session: Session = Depends(get_db_session)) -> TaskGroupRepository:
    return TaskGroupRepository(session)


def get_task_group_service(
    repository: TaskGroupRepository = Depends(get_task_group_repository),
    task_service: TaskService = Depends(get_task_service),
    group_service: GroupService = Depends(get_group_service),
    user_service: UserService = Depends(get_user_service),
    user_group_service: UserGroupService = Depends(get_user_group_service),
) -> TaskGroupService:
    return TaskGroupService(
        repository, task_service, group_service, user_service, user_group_service
    )
```

- [ ] **Step 12: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: PASS — every test in `tests/unit`, `tests/integration`, and `tests/repositories`, all now running against real Postgres. This is the first point since Task 2 where the full suite is exercised end-to-end with zero in-memory code left; if anything fails, check for a leftover `InMemory*` reference (e.g. a forgotten import) before anything else.

- [ ] **Step 13: Manual smoke test against the real database**

Run: `.venv/bin/uvicorn app.main:app --reload` (one terminal), then in another:
```bash
USER_ID=$(curl -s -X POST http://127.0.0.1:8000/api/v1/users -H "Content-Type: application/json" -d '{"firstName":"Ada","lastName":"Lovelace"}' | python3 -c "import json,sys;print(json.load(sys.stdin)['userId'])")
GROUP_ID=$(curl -s -X POST http://127.0.0.1:8000/api/v1/groups -H "Content-Type: application/json" -d "{\"groupName\":\"Smiths\",\"groupCategory\":\"Family\",\"groupCreaterId\":\"$USER_ID\"}" | python3 -c "import json,sys;print(json.load(sys.stdin)['groupId'])")
curl -s -X POST http://127.0.0.1:8000/api/v1/groups/$GROUP_ID/members -H "Content-Type: application/json" -d "{\"userId\":\"$USER_ID\",\"relationship\":\"Father\"}"
/opt/homebrew/opt/postgresql@17/bin/psql tasks_net_db -c "select * from users; select * from groups; select * from user_groups;"
```
Expected: `psql` output shows the created user, group, and user_group row.

- [ ] **Step 14: Commit**

```bash
git add app/repositories/ app/services/group_service.py app/services/user_group_service.py app/services/task_group_service.py app/dependencies.py tests/unit/ tests/conftest.py
git commit -m "feat: remove in-memory repositories, wire the app entirely to PostgreSQL"
```

---

## Task 9: Documentation

**Files:**
- Modify: `OpenPoints.md`
- Modify: `Arch.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: everything from Tasks 1-8.
- Produces: nothing (terminal task).

- [ ] **Step 1: Update `OpenPoints.md`'s Persistence section**

Change:
```markdown
## Persistence
- All data lives in in-process Python dicts and is lost on restart or
  process crash. No database is wired up yet (explicitly out of scope per
  `requirements.md`). When a DB is introduced, only new repository classes
  implementing `BaseRepository[T]` should be needed — see `Arch.md`.
- Repositories are not thread-safe / process-safe. Running with multiple
  Uvicorn workers will give each worker its own independent in-memory state.
  Fine for local dev/demo; must be fixed (shared store or single worker)
  before any multi-worker deployment.
```
to:
```markdown
## Persistence
- The app is backed entirely by PostgreSQL 17 via SQLAlchemy + psycopg3,
  with Alembic managing schema migrations (`migrations/`). No in-memory
  storage remains anywhere in the codebase, including tests — the full
  suite (`tests/unit`, `tests/integration`, `tests/repositories`) requires
  a running local Postgres (`tasks_net_db_test`).
- `docker-compose.yml` does not run Postgres — local development targets
  the Postgres 17 instance installed via Homebrew (`brew services start
  postgresql@17`). Revisit if/when this needs to run in Docker.
```

- [ ] **Step 2: Update `Arch.md`'s Dependency Injection section**

Change:
```markdown
`app/dependencies.py` is the only place that constructs concrete repository
and service instances. Repository providers are `@lru_cache`d so the app
uses one singleton per repository per process (in-memory data must persist
across requests within a process). Services are built fresh per-request by
composing the cached repositories via FastAPI's `Depends`.
```
to:
```markdown
`app/dependencies.py` is the only place that constructs concrete repository
and service instances. Repository providers build a repository per request
from a SQLAlchemy `Session` (`app/db/session.get_db_session`, itself a
`Depends`), so every repository used within one request shares one
`Session`/transaction, committed or rolled back atomically at the end of
the request. Services are built fresh per-request by composing the
per-request repositories via FastAPI's `Depends`.
```

- [ ] **Step 3: Update `README.md`'s PostgreSQL section**

Change:
```markdown
## PostgreSQL (local, for future DB work)

The app currently uses in-memory storage only — no code connects to
Postgres yet (see `OpenPoints.md`). PostgreSQL 17 is installed locally via
Homebrew in preparation for that work.
```
to:
```markdown
## PostgreSQL

The app is backed entirely by PostgreSQL 17 via SQLAlchemy + psycopg3, with
Alembic managing schema migrations. PostgreSQL 17 is installed locally via
Homebrew.
```
and, after the existing install/start/stop/status commands, add:
```markdown
### Database setup (one-time)

    createdb tasks_net_db
    createdb tasks_net_db_test
    alembic upgrade head

### Running the test suite

The full suite (`pytest -v`) requires the local Postgres service to be
running (`brew services start postgresql@17`) and both databases created.
```

- [ ] **Step 4: Run the full suite one more time**

Run: `.venv/bin/pytest -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add OpenPoints.md Arch.md README.md
git commit -m "docs: describe the PostgreSQL-only composition root"
```

---

## Self-Review

**Spec coverage:** `ASK.md`'s Postgres 17/psycopg3/SQLAlchemy prereqs → Task 1. Table names/PK/FK/index → Task 2. All 5 repositories → Tasks 3-7. Removing in-memory entirely + rewriting existing tests (this session's refinement) → Task 8. No gaps found.

**Placeholder scan:** every step has literal code, exact file paths, or an exact command with expected output.

**Type consistency:** `UserRepository`/`TaskRepository`/`GroupRepository`/`UserGroupRepository`/`TaskGroupRepository` constructor signatures (`session: Session`) are identical everywhere they're defined (Tasks 3-7) and consumed (Task 8's service fixtures, `client` fixture, and `app/dependencies.py`). `GroupRepository.list_by_creator`, `UserGroupRepository.find_by_user_and_group`/`list_by_group`/`delete`, `TaskGroupRepository.find_by_task_and_group` are named identically in their Task 3-7 definitions and nowhere else referenced under different names.
