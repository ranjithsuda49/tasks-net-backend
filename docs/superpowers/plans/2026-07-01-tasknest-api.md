# TaskNest REST API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastAPI-based backend (v1 REST APIs) for TaskNest — a task-management service with Users, Groups, Tasks, and their relationships — backed entirely by in-memory storage, structured around SOLID principles so a persistent DB can be swapped in later without touching business logic.

**Architecture:** Layered-by-responsibility: `api` (FastAPI routers, HTTP concerns only) → `services` (business logic, depends only on repository abstractions) → `repositories` (abstract interface + in-memory implementation, one pair per entity) → `models`/`schemas` (domain models vs. API request/response contracts). Dependency Inversion is achieved via FastAPI's `Depends` wiring concrete in-memory repositories into services at the composition root (`app/dependencies.py`).

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, Uvicorn, pytest, httpx (for `TestClient`), pip + `requirements.txt`.

## Global Constraints

- IDs (`userId`, `groupId`, `taskId`, and relationship `uuid`s) are UUID4 strings generated server-side — never client-supplied.
- No database — all persistence is in-process Python dicts inside repository classes; data is lost on restart (document this in `OpenPoints.md`).
- Strict SOLID adherence: services depend on abstract repository interfaces (`ABC`), never on concrete `InMemory*Repository` classes directly.
- All endpoints are versioned under `/api/v1/...`.
- Dependency management via `pip` + a single `requirements.txt` (no Poetry/uv).
- Every service method and router must have both a unit test (service/repository level) and an integration test (HTTP level via `TestClient`) — per the spec's Testing Plan section.
- `Arch.md` and `OpenPoints.md` must exist at the repo root and stay accurate as the codebase grows.

---

## Context

`requirements.md` describes TaskNest: a backend for Users creating/updating/deleting Tasks, where Users can optionally belong to Groups and Tasks can optionally be associated with Groups. The directory currently contains only `requirements.md` — this is a greenfield build. The user has decided (via clarifying questions): UUID4 string IDs, `pip`/`requirements.txt` tooling, and a layered-by-responsibility folder structure. The plan below builds the five entities (User, Group, User-Group relationship, Task, Task-Group relationship) as vertical slices, each with its own repository, service, schema, router, and tests, wired together through a small dependency-injection composition root — enabling later replacement of in-memory repositories with real DB-backed ones without touching services or routers.

---

## File Structure

```
Tasks_Nest/
├── requirements.md
├── requirements.txt
├── Arch.md
├── OpenPoints.md
├── pytest.ini
├── app/
│   ├── __init__.py
│   ├── main.py                        # FastAPI app instance, router registration
│   ├── exceptions.py                  # NotFoundError, ConflictError
│   ├── dependencies.py                # composition root: repo + service providers
│   ├── models/
│   │   ├── __init__.py
│   │   ├── enums.py                   # UserStatus, GroupStatus, TaskState
│   │   ├── user.py                    # User, Name domain models
│   │   ├── group.py                   # Group domain model
│   │   ├── user_group.py              # UserGroupRelationship domain model
│   │   ├── task.py                    # Task domain model
│   │   └── task_group.py              # TaskGroupRelationship domain model
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── base.py                    # BaseRepository[T] ABC
│   │   ├── user_repository.py
│   │   ├── group_repository.py
│   │   ├── user_group_repository.py
│   │   ├── task_repository.py
│   │   └── task_group_repository.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── user_service.py
│   │   ├── group_service.py
│   │   ├── user_group_service.py
│   │   ├── task_service.py
│   │   └── task_group_service.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── group.py
│   │   ├── user_group.py
│   │   ├── task.py
│   │   └── task_group.py
│   └── api/
│       ├── __init__.py
│       └── v1/
│           ├── __init__.py
│           ├── users.py
│           ├── groups.py
│           ├── user_group.py
│           ├── tasks.py
│           └── task_group.py
└── tests/
    ├── __init__.py
    ├── conftest.py                    # shared `client` fixture with fresh in-memory state
    ├── unit/
    │   ├── __init__.py
    │   ├── test_user_service.py
    │   ├── test_group_service.py
    │   ├── test_user_group_service.py
    │   ├── test_task_service.py
    │   └── test_task_group_service.py
    └── integration/
        ├── __init__.py
        ├── test_users_api.py
        ├── test_groups_api.py
        ├── test_user_group_api.py
        ├── test_tasks_api.py
        └── test_task_group_api.py
```

---

## Task 1: Project Scaffolding, Shared Building Blocks, Arch.md & OpenPoints.md

**Files:**
- Create: `requirements.txt`
- Create: `pytest.ini`
- Create: `app/__init__.py`, `app/main.py`
- Create: `app/exceptions.py`
- Create: `app/models/__init__.py`, `app/models/enums.py`
- Create: `app/repositories/__init__.py`, `app/repositories/base.py`
- Create: `Arch.md`
- Create: `OpenPoints.md`
- Test: `tests/__init__.py`, `tests/test_app_smoke.py`

**Interfaces:**
- Produces: `UserStatus`, `GroupStatus`, `TaskState` (str Enums, `app/models/enums.py`) — consumed by every model/schema/service task below.
- Produces: `NotFoundError(message: str)`, `ConflictError(message: str)` (`app/exceptions.py`) — raised by all services, caught by all routers.
- Produces: `BaseRepository[T]` ABC with abstract methods `add(entity: T) -> T`, `get(entity_id: str) -> Optional[T]`, `update(entity: T) -> T`, `list_all() -> list[T]` (`app/repositories/base.py`) — implemented by every concrete repository.
- Produces: `app.main.app` — the FastAPI instance later tasks register routers on.

- [ ] **Step 1: Create the directory skeleton and `requirements.txt`**

Run:
```bash
mkdir -p app/models app/repositories app/services app/schemas app/api/v1
mkdir -p tests/unit tests/integration
touch app/__init__.py app/models/__init__.py app/repositories/__init__.py \
      app/services/__init__.py app/schemas/__init__.py app/api/__init__.py \
      app/api/v1/__init__.py tests/__init__.py tests/unit/__init__.py \
      tests/integration/__init__.py
```

Write `requirements.txt`:
```
fastapi==0.115.6
uvicorn[standard]==0.34.0
pydantic==2.10.4
pytest==8.3.4
httpx==0.28.1
```

- [ ] **Step 2: Create a virtualenv and install dependencies**

Run:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Expected: install completes with no errors; `pip show fastapi` reports version `0.115.6`.

- [ ] **Step 3: Write `pytest.ini`**

```ini
[pytest]
pythonpath = .
testpaths = tests
```

- [ ] **Step 4: Write `app/models/enums.py`**

```python
from enum import Enum


class UserStatus(str, Enum):
    ACTIVE = "ACTIVE"
    IN_ACTIVE = "IN-ACTIVE"


class GroupStatus(str, Enum):
    ACTIVE = "ACTIVE"
    IN_ACTIVE = "IN-ACTIVE"


class TaskState(str, Enum):
    TODO = "TODO"
    IN_PROGRESS = "IN-PROGRESS"
    COMPLETED = "COMPLETED"
```

- [ ] **Step 5: Write `app/exceptions.py`**

```python
class NotFoundError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ConflictError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)
```

- [ ] **Step 6: Write `app/repositories/base.py`**

```python
from abc import ABC, abstractmethod
from typing import Generic, Optional, TypeVar

T = TypeVar("T")


class BaseRepository(ABC, Generic[T]):
    @abstractmethod
    def add(self, entity: T) -> T:
        ...

    @abstractmethod
    def get(self, entity_id: str) -> Optional[T]:
        ...

    @abstractmethod
    def update(self, entity: T) -> T:
        ...

    @abstractmethod
    def list_all(self) -> list[T]:
        ...
```

- [ ] **Step 7: Write `app/main.py` (skeleton — routers added in later tasks)**

```python
from fastapi import FastAPI

app = FastAPI(title="TaskNest", version="1.0.0")


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 8: Write the failing smoke test**

```python
# tests/test_app_smoke.py
from fastapi.testclient import TestClient

from app.main import app


def test_health_check_returns_ok():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 9: Run the smoke test to verify it passes**

Run: `pytest tests/test_app_smoke.py -v`
Expected: `PASS` (1 passed) — this test should already pass since `main.py` was written in Step 7; it exists to prove the toolchain and `pythonpath` config work end-to-end before building further.

- [ ] **Step 10: Write `Arch.md`**

```markdown
# TaskNest — Architecture

## Layers

1. **api/v1** — FastAPI routers. Only HTTP concerns: request parsing, status
   codes, translating domain exceptions to `HTTPException`. No business logic.
2. **services** — Business logic. Each service takes one or more
   `BaseRepository` abstractions in its constructor (constructor injection),
   never a concrete `InMemory*Repository`. This is the Dependency Inversion
   seam: swapping in-memory storage for a real DB later means writing new
   repository classes only — services and routers do not change.
3. **repositories** — `BaseRepository[T]` (abstract) defines `add`, `get`,
   `update`, `list_all`. `InMemory*Repository` classes implement it with a
   `dict[str, T]` keyed by entity ID. One repository per entity/relationship.
4. **models** — Domain entities (Pydantic models), the shape of truth held by
   repositories.
5. **schemas** — API request/response contracts (Pydantic models), decoupled
   from domain models so the wire format can evolve independently of the
   internal shape.

## Dependency Injection / Composition Root

`app/dependencies.py` is the only place that constructs concrete repository
and service instances. Repository providers are `@lru_cache`d so the app
uses one singleton per repository per process (in-memory data must persist
across requests within a process). Services are built fresh per-request by
composing the cached repositories via FastAPI's `Depends`.

Tests override the service-level provider functions (via
`app.dependency_overrides`) with a shared set of freshly constructed
repositories/services per test, so tests never see state from other tests
and cross-entity integration tests (e.g. create a user, then a group
referencing it) still share consistent state within a single test.

## SOLID mapping

- **S**: routers, services, and repositories each have exactly one reason to
  change (HTTP shape, business rule, storage mechanism respectively).
- **O**: new repository implementations (e.g. a future `SqlUserRepository`)
  can be added without modifying `UserService`.
- **L**: any `BaseRepository[T]` implementation is substitutable wherever a
  service expects one — enforced by the shared abstract base.
- **I**: repository interfaces are per-entity rather than one large
  interface, so no repository is forced to implement methods it doesn't need.
- **D**: services and routers depend on abstractions (`BaseRepository`,
  injected via `Depends`), never on concrete in-memory classes.

## Entity relationships

- `User` 1—0..N `UserGroupRelationship` N—1 `Group` (many-to-many join with
  a `relationship` label, e.g. "Father").
- `Task` 0..1—0..N `TaskGroupRelationship` N—0..1 `Group`, with an optional
  `assigneeId` (a `User`) on each join row.

## Request flow example (create user)

`POST /api/v1/users` → `api/v1/users.create_user` → `UserService.create_user`
(generates UUID4, timestamps, builds `User` domain model) →
`InMemoryUserRepository.add` (stores in dict) → router maps `User` domain
model to `UserResponse` schema → FastAPI serializes to JSON.

## Testing strategy

- **Unit tests** (`tests/unit/`) instantiate a service directly with a fresh
  `InMemory*Repository`, bypassing HTTP entirely.
- **Integration tests** (`tests/integration/`) use FastAPI's `TestClient`
  against the real app with `app.dependency_overrides` pointed at
  freshly-constructed repositories/services per test (see
  `tests/conftest.py`), exercising the full router → service → repository
  path.
```

- [ ] **Step 11: Write `OpenPoints.md`**

```markdown
# TaskNest — Open Points / Future Work

Tracked gaps and decisions deferred during the initial build. Revisit these
before any production use.

## Persistence
- All data lives in in-process Python dicts and is lost on restart or
  process crash. No database is wired up yet (explicitly out of scope per
  `requirements.md`). When a DB is introduced, only new repository classes
  implementing `BaseRepository[T]` should be needed — see `Arch.md`.
- Repositories are not thread-safe / process-safe. Running with multiple
  Uvicorn workers will give each worker its own independent in-memory state.
  Fine for local dev/demo; must be fixed (shared store or single worker)
  before any multi-worker deployment.

## Auth & authorization
- No authentication or authorization exists on any endpoint. Anyone can
  create/update any user, group, or task, or assign tasks to arbitrary
  users. Needs a decision on auth scheme (session, JWT, API key) before
  this is exposed beyond local development.

## Validation gaps
- Assigning a task to a user in `Task-Group-Relationship` does not verify
  the assignee is actually a member of the target group (no cross-check
  against `UserGroupRelationship`).
- Task state transitions (`TaskState`) are unrestricted — any state can move
  to any other state (e.g. `COMPLETED` → `TODO` is allowed). No workflow
  rules are enforced. Revisit if the product needs a strict state machine.
- No uniqueness check preventing the same user being added to the same
  group twice with two different `UserGroupRelationship` rows.

## API surface gaps
- No delete endpoints for `User` or `Group` (spec only asks for status
  toggling, not hard delete) — confirm this is intentional product
  behavior, not an oversight.
- No pagination, filtering, or sorting on list endpoints (e.g.
  "fetch all groups created by user") — fine at small scale, will need
  pagination once data volume grows.
- No bulk operations (e.g. bulk task creation/assignment).

## Observability & ops
- No structured logging, request tracing, or metrics.
- No rate limiting.
- No OpenAPI examples/descriptions beyond FastAPI's auto-generated schema
  from Pydantic models — worth enriching for consumers once the API
  stabilizes.

## Testing
- Unit and integration tests cover the happy paths and documented error
  paths (404s) for each entity. Concurrency/race-condition testing on the
  in-memory stores is not covered.
```

- [ ] **Step 12: Commit**

```bash
git init
git add app tests requirements.txt pytest.ini Arch.md OpenPoints.md requirements.md .gitignore 2>/dev/null || \
git add app tests requirements.txt pytest.ini Arch.md OpenPoints.md requirements.md
git commit -m "chore: scaffold TaskNest FastAPI project with shared building blocks"
```

Note: this repo has no `.gitignore` yet — before committing, create one excluding `.venv/`, `__pycache__/`, and `.pytest_cache/`:
```bash
printf '.venv/\n__pycache__/\n*.pyc\n.pytest_cache/\n' > .gitignore
git add .gitignore
```

---

## Task 2: User Entity (Model, Repository, Service, Schema, Router)

**Files:**
- Create: `app/models/user.py`
- Create: `app/repositories/user_repository.py`
- Create: `app/services/user_service.py`
- Create: `app/schemas/user.py`
- Create: `app/api/v1/users.py`
- Modify: `app/dependencies.py` (new file — created here since this is the first service needing DI)
- Modify: `app/main.py` (register the users router)
- Test: `tests/unit/test_user_service.py`
- Test: `tests/integration/test_users_api.py`
- Test: `tests/conftest.py` (new file — created here since this is the first integration test)

**Interfaces:**
- Consumes: `UserStatus` (`app/models/enums.py`), `BaseRepository[T]` (`app/repositories/base.py`), `NotFoundError` (`app/exceptions.py`) from Task 1.
- Produces: `User`, `Name` domain models (`app/models/user.py`) — consumed by Task 3 (`Group.groupCreaterId` validation) and Task 4/6 (assignee/user validation).
- Produces: `UserService(repository: BaseRepository[User])` with methods `create_user(first_name, last_name, phone_num=None, email_id=None) -> User`, `get_user(user_id: str) -> User`, `update_user(user_id, first_name=None, last_name=None, phone_num=None, email_id=None) -> User`, `set_status(user_id: str, status: UserStatus) -> User` — consumed by Task 3/4/6 services for existence checks.
- Produces: `get_user_repository() -> InMemoryUserRepository` and `get_user_service() -> UserService` in `app/dependencies.py` — consumed by Tasks 3–6's own `dependencies.py` additions.
- Produces: `tests/conftest.py::client` fixture — consumed by every integration test file in Tasks 3–6.

- [ ] **Step 1: Write the domain model** `app/models/user.py`

```python
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.enums import UserStatus


class Name(BaseModel):
    firstName: str
    lastName: str


class User(BaseModel):
    userId: str
    name: Name
    phoneNum: Optional[str] = None
    emailId: Optional[str] = None
    userStatus: UserStatus = UserStatus.ACTIVE
    createdAt: datetime
    updatedAt: Optional[datetime] = None
```

- [ ] **Step 2: Write the repository** `app/repositories/user_repository.py`

```python
from typing import Optional

from app.models.user import User
from app.repositories.base import BaseRepository


class InMemoryUserRepository(BaseRepository[User]):
    def __init__(self) -> None:
        self._store: dict[str, User] = {}

    def add(self, entity: User) -> User:
        self._store[entity.userId] = entity
        return entity

    def get(self, entity_id: str) -> Optional[User]:
        return self._store.get(entity_id)

    def update(self, entity: User) -> User:
        self._store[entity.userId] = entity
        return entity

    def list_all(self) -> list[User]:
        return list(self._store.values())
```

- [ ] **Step 3: Write the failing unit test for the service** `tests/unit/test_user_service.py`

```python
import pytest

from app.exceptions import NotFoundError
from app.models.enums import UserStatus
from app.repositories.user_repository import InMemoryUserRepository
from app.services.user_service import UserService


@pytest.fixture
def service() -> UserService:
    return UserService(InMemoryUserRepository())


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
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `pytest tests/unit/test_user_service.py -v`
Expected: `FAIL` — `ModuleNotFoundError: No module named 'app.services.user_service'`

- [ ] **Step 5: Write the service** `app/services/user_service.py`

```python
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.exceptions import NotFoundError
from app.models.enums import UserStatus
from app.models.user import Name, User
from app.repositories.base import BaseRepository


class UserService:
    def __init__(self, repository: BaseRepository[User]):
        self._repository = repository

    def create_user(
        self,
        first_name: str,
        last_name: str,
        phone_num: Optional[str] = None,
        email_id: Optional[str] = None,
    ) -> User:
        now = datetime.now(timezone.utc)
        user = User(
            userId=str(uuid.uuid4()),
            name=Name(firstName=first_name, lastName=last_name),
            phoneNum=phone_num,
            emailId=email_id,
            userStatus=UserStatus.ACTIVE,
            createdAt=now,
            updatedAt=None,
        )
        return self._repository.add(user)

    def get_user(self, user_id: str) -> User:
        user = self._repository.get(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found")
        return user

    def update_user(
        self,
        user_id: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        phone_num: Optional[str] = None,
        email_id: Optional[str] = None,
    ) -> User:
        user = self.get_user(user_id)
        updated = user.model_copy(
            update={
                "name": Name(
                    firstName=first_name if first_name is not None else user.name.firstName,
                    lastName=last_name if last_name is not None else user.name.lastName,
                ),
                "phoneNum": phone_num if phone_num is not None else user.phoneNum,
                "emailId": email_id if email_id is not None else user.emailId,
                "updatedAt": datetime.now(timezone.utc),
            }
        )
        return self._repository.update(updated)

    def set_status(self, user_id: str, status: UserStatus) -> User:
        user = self.get_user(user_id)
        updated = user.model_copy(
            update={"userStatus": status, "updatedAt": datetime.now(timezone.utc)}
        )
        return self._repository.update(updated)
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `pytest tests/unit/test_user_service.py -v`
Expected: `PASS` (5 passed)

- [ ] **Step 7: Write the API schemas** `app/schemas/user.py`

```python
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.enums import UserStatus


class NameSchema(BaseModel):
    firstName: str
    lastName: str


class UserCreateRequest(BaseModel):
    firstName: str
    lastName: str
    phoneNum: Optional[str] = None
    emailId: Optional[str] = None


class UserUpdateRequest(BaseModel):
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    phoneNum: Optional[str] = None
    emailId: Optional[str] = None


class UserStatusUpdateRequest(BaseModel):
    userStatus: UserStatus


class UserResponse(BaseModel):
    userId: str
    name: NameSchema
    phoneNum: Optional[str] = None
    emailId: Optional[str] = None
    userStatus: UserStatus
    createdAt: datetime
    updatedAt: Optional[datetime] = None
```

- [ ] **Step 8: Write `app/dependencies.py` (composition root, User section only for now)**

```python
from functools import lru_cache

from app.repositories.user_repository import InMemoryUserRepository
from app.services.user_service import UserService


@lru_cache
def get_user_repository() -> InMemoryUserRepository:
    return InMemoryUserRepository()


def get_user_service() -> UserService:
    return UserService(get_user_repository())
```

- [ ] **Step 9: Write the router** `app/api/v1/users.py`

```python
from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_user_service
from app.exceptions import NotFoundError
from app.models.user import User
from app.schemas.user import (
    NameSchema,
    UserCreateRequest,
    UserResponse,
    UserStatusUpdateRequest,
    UserUpdateRequest,
)
from app.services.user_service import UserService

router = APIRouter(prefix="/api/v1/users", tags=["users"])


def _to_response(user: User) -> UserResponse:
    return UserResponse(
        userId=user.userId,
        name=NameSchema(firstName=user.name.firstName, lastName=user.name.lastName),
        phoneNum=user.phoneNum,
        emailId=user.emailId,
        userStatus=user.userStatus,
        createdAt=user.createdAt,
        updatedAt=user.updatedAt,
    )


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreateRequest, service: UserService = Depends(get_user_service)
) -> UserResponse:
    user = service.create_user(
        first_name=payload.firstName,
        last_name=payload.lastName,
        phone_num=payload.phoneNum,
        email_id=payload.emailId,
    )
    return _to_response(user)


@router.get("/{user_id}", response_model=UserResponse)
def get_user(user_id: str, service: UserService = Depends(get_user_service)) -> UserResponse:
    try:
        user = service.get_user(user_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_response(user)


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: str, payload: UserUpdateRequest, service: UserService = Depends(get_user_service)
) -> UserResponse:
    try:
        user = service.update_user(
            user_id,
            first_name=payload.firstName,
            last_name=payload.lastName,
            phone_num=payload.phoneNum,
            email_id=payload.emailId,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_response(user)


@router.patch("/{user_id}/status", response_model=UserResponse)
def update_user_status(
    user_id: str,
    payload: UserStatusUpdateRequest,
    service: UserService = Depends(get_user_service),
) -> UserResponse:
    try:
        user = service.set_status(user_id, payload.userStatus)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_response(user)
```

- [ ] **Step 10: Register the router in `app/main.py`**

```python
from fastapi import FastAPI

from app.api.v1.users import router as users_router

app = FastAPI(title="TaskNest", version="1.0.0")

app.include_router(users_router)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 11: Write `tests/conftest.py`**

```python
import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_user_service
from app.main import app
from app.repositories.user_repository import InMemoryUserRepository
from app.services.user_service import UserService


@pytest.fixture
def client():
    user_repo = InMemoryUserRepository()
    user_service = UserService(user_repo)

    app.dependency_overrides[get_user_service] = lambda: user_service

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
```

- [ ] **Step 12: Write the failing integration test** `tests/integration/test_users_api.py`

```python
def test_create_and_fetch_user(client):
    create_response = client.post(
        "/api/v1/users",
        json={"firstName": "Ada", "lastName": "Lovelace", "emailId": "ada@example.com"},
    )
    assert create_response.status_code == 201
    body = create_response.json()
    assert body["name"] == {"firstName": "Ada", "lastName": "Lovelace"}
    assert body["userStatus"] == "ACTIVE"
    user_id = body["userId"]

    fetch_response = client.get(f"/api/v1/users/{user_id}")
    assert fetch_response.status_code == 200
    assert fetch_response.json()["userId"] == user_id


def test_fetch_unknown_user_returns_404(client):
    response = client.get("/api/v1/users/does-not-exist")
    assert response.status_code == 404


def test_update_user_fields(client):
    user_id = client.post(
        "/api/v1/users", json={"firstName": "Ada", "lastName": "Lovelace"}
    ).json()["userId"]

    response = client.patch(f"/api/v1/users/{user_id}", json={"lastName": "King"})
    assert response.status_code == 200
    assert response.json()["name"]["lastName"] == "King"


def test_update_user_status(client):
    user_id = client.post(
        "/api/v1/users", json={"firstName": "Ada", "lastName": "Lovelace"}
    ).json()["userId"]

    response = client.patch(
        f"/api/v1/users/{user_id}/status", json={"userStatus": "IN-ACTIVE"}
    )
    assert response.status_code == 200
    assert response.json()["userStatus"] == "IN-ACTIVE"
```

- [ ] **Step 13: Run the integration tests to verify they fail, then pass**

Run: `pytest tests/integration/test_users_api.py -v`
Expected before router/conftest existed: import errors; after Steps 9–12 are in place: `PASS` (4 passed). Run it now and confirm `PASS`.

- [ ] **Step 14: Run the full suite**

Run: `pytest -v`
Expected: all tests pass (smoke + user unit + user integration).

- [ ] **Step 15: Commit**

```bash
git add app tests
git commit -m "feat: add User entity CRUD (model, repository, service, API)"
```

---

## Task 3: Group Entity (Model, Repository, Service, Schema, Router)

**Files:**
- Create: `app/models/group.py`
- Create: `app/repositories/group_repository.py`
- Create: `app/services/group_service.py`
- Create: `app/schemas/group.py`
- Create: `app/api/v1/groups.py`
- Modify: `app/dependencies.py` (add group providers)
- Modify: `app/main.py` (register groups router)
- Modify: `tests/conftest.py` (wire group service override)
- Test: `tests/unit/test_group_service.py`
- Test: `tests/integration/test_groups_api.py`

**Interfaces:**
- Consumes: `GroupStatus` (Task 1), `BaseRepository[T]`, `NotFoundError` (Task 1); `User`, `UserService.get_user` (Task 2) — to validate `groupCreaterId` exists.
- Produces: `Group` domain model (`app/models/group.py`) — consumed by Task 4 and Task 6.
- Produces: `GroupService(repository: BaseRepository[Group], user_repository: BaseRepository[User])` with methods `create_group(group_name, group_desc, group_category, creater_id, group_icon_url=None) -> Group`, `get_group(group_id: str) -> Group`, `get_groups_by_creator(user_id: str) -> list[Group]`, `update_group(group_id, group_name=None, group_desc=None, group_icon_url=None) -> Group`, `set_status(group_id: str, status: GroupStatus) -> Group` — consumed by Task 4/6 services for existence checks.
- Produces: `get_group_repository() -> InMemoryGroupRepository`, `get_group_service() -> GroupService` in `app/dependencies.py` — consumed by Task 4/6's `dependencies.py` additions.

- [ ] **Step 1: Write the domain model** `app/models/group.py`

```python
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.enums import GroupStatus


class Group(BaseModel):
    groupId: str
    groupName: str
    groupDesc: Optional[str] = None
    groupCategory: str
    groupStatus: GroupStatus = GroupStatus.ACTIVE
    groupIconUrl: Optional[str] = None
    groupCreaterId: str
    createdAt: datetime
    updatedAt: Optional[datetime] = None
```

- [ ] **Step 2: Write the repository** `app/repositories/group_repository.py`

```python
from typing import Optional

from app.models.group import Group
from app.repositories.base import BaseRepository


class InMemoryGroupRepository(BaseRepository[Group]):
    def __init__(self) -> None:
        self._store: dict[str, Group] = {}

    def add(self, entity: Group) -> Group:
        self._store[entity.groupId] = entity
        return entity

    def get(self, entity_id: str) -> Optional[Group]:
        return self._store.get(entity_id)

    def update(self, entity: Group) -> Group:
        self._store[entity.groupId] = entity
        return entity

    def list_all(self) -> list[Group]:
        return list(self._store.values())

    def list_by_creator(self, creater_id: str) -> list[Group]:
        return [group for group in self._store.values() if group.groupCreaterId == creater_id]
```

- [ ] **Step 3: Write the failing unit test** `tests/unit/test_group_service.py`

```python
import pytest

from app.exceptions import NotFoundError
from app.models.enums import GroupStatus
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
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `pytest tests/unit/test_group_service.py -v`
Expected: `FAIL` — `ModuleNotFoundError: No module named 'app.services.group_service'`

- [ ] **Step 5: Write the service** `app/services/group_service.py`

```python
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.exceptions import NotFoundError
from app.models.enums import GroupStatus
from app.models.group import Group
from app.repositories.base import BaseRepository
from app.repositories.group_repository import InMemoryGroupRepository
from app.services.user_service import UserService


class GroupService:
    def __init__(self, repository: InMemoryGroupRepository, user_service: UserService):
        self._repository = repository
        self._user_service = user_service

    def create_group(
        self,
        group_name: str,
        group_desc: Optional[str],
        group_category: str,
        creater_id: str,
        group_icon_url: Optional[str] = None,
    ) -> Group:
        self._user_service.get_user(creater_id)
        now = datetime.now(timezone.utc)
        group = Group(
            groupId=str(uuid.uuid4()),
            groupName=group_name,
            groupDesc=group_desc,
            groupCategory=group_category,
            groupStatus=GroupStatus.ACTIVE,
            groupIconUrl=group_icon_url,
            groupCreaterId=creater_id,
            createdAt=now,
            updatedAt=None,
        )
        return self._repository.add(group)

    def get_group(self, group_id: str) -> Group:
        group = self._repository.get(group_id)
        if group is None:
            raise NotFoundError(f"Group {group_id} not found")
        return group

    def get_groups_by_creator(self, creater_id: str) -> list[Group]:
        return self._repository.list_by_creator(creater_id)

    def update_group(
        self,
        group_id: str,
        group_name: Optional[str] = None,
        group_desc: Optional[str] = None,
        group_icon_url: Optional[str] = None,
    ) -> Group:
        group = self.get_group(group_id)
        updated = group.model_copy(
            update={
                "groupName": group_name if group_name is not None else group.groupName,
                "groupDesc": group_desc if group_desc is not None else group.groupDesc,
                "groupIconUrl": group_icon_url if group_icon_url is not None else group.groupIconUrl,
                "updatedAt": datetime.now(timezone.utc),
            }
        )
        return self._repository.update(updated)

    def set_status(self, group_id: str, status: GroupStatus) -> Group:
        group = self.get_group(group_id)
        updated = group.model_copy(
            update={"groupStatus": status, "updatedAt": datetime.now(timezone.utc)}
        )
        return self._repository.update(updated)
```

Note: `GroupService` depends on the concrete `InMemoryGroupRepository` type hint for `list_by_creator`, since that query is Group-specific and not part of the generic `BaseRepository[T]` interface — this keeps `BaseRepository` free of entity-specific methods while still allowing each repository to expose extra query methods its service needs. `GroupService` depends on `UserService` (not `BaseRepository[User]` directly) because the creator-existence check is itself a business rule belonging to the user domain, and reusing `UserService.get_user` avoids duplicating the not-found logic.

- [ ] **Step 6: Run the test to verify it passes**

Run: `pytest tests/unit/test_group_service.py -v`
Expected: `PASS` (5 passed)

- [ ] **Step 7: Write the schemas** `app/schemas/group.py`

```python
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.enums import GroupStatus


class GroupCreateRequest(BaseModel):
    groupName: str
    groupDesc: Optional[str] = None
    groupCategory: str
    groupCreaterId: str
    groupIconUrl: Optional[str] = None


class GroupUpdateRequest(BaseModel):
    groupName: Optional[str] = None
    groupDesc: Optional[str] = None
    groupIconUrl: Optional[str] = None


class GroupStatusUpdateRequest(BaseModel):
    groupStatus: GroupStatus


class GroupResponse(BaseModel):
    groupId: str
    groupName: str
    groupDesc: Optional[str] = None
    groupCategory: str
    groupStatus: GroupStatus
    groupIconUrl: Optional[str] = None
    groupCreaterId: str
    createdAt: datetime
    updatedAt: Optional[datetime] = None
```

- [ ] **Step 8: Extend `app/dependencies.py`**

```python
from functools import lru_cache

from app.repositories.group_repository import InMemoryGroupRepository
from app.repositories.user_repository import InMemoryUserRepository
from app.services.group_service import GroupService
from app.services.user_service import UserService


@lru_cache
def get_user_repository() -> InMemoryUserRepository:
    return InMemoryUserRepository()


def get_user_service() -> UserService:
    return UserService(get_user_repository())


@lru_cache
def get_group_repository() -> InMemoryGroupRepository:
    return InMemoryGroupRepository()


def get_group_service() -> GroupService:
    return GroupService(get_group_repository(), get_user_service())
```

- [ ] **Step 9: Write the router** `app/api/v1/groups.py`

```python
from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_group_service
from app.exceptions import NotFoundError
from app.models.group import Group
from app.schemas.group import (
    GroupCreateRequest,
    GroupResponse,
    GroupStatusUpdateRequest,
    GroupUpdateRequest,
)
from app.services.group_service import GroupService

router = APIRouter(prefix="/api/v1", tags=["groups"])


def _to_response(group: Group) -> GroupResponse:
    return GroupResponse(
        groupId=group.groupId,
        groupName=group.groupName,
        groupDesc=group.groupDesc,
        groupCategory=group.groupCategory,
        groupStatus=group.groupStatus,
        groupIconUrl=group.groupIconUrl,
        groupCreaterId=group.groupCreaterId,
        createdAt=group.createdAt,
        updatedAt=group.updatedAt,
    )


@router.post("/groups", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
def create_group(
    payload: GroupCreateRequest, service: GroupService = Depends(get_group_service)
) -> GroupResponse:
    try:
        group = service.create_group(
            group_name=payload.groupName,
            group_desc=payload.groupDesc,
            group_category=payload.groupCategory,
            creater_id=payload.groupCreaterId,
            group_icon_url=payload.groupIconUrl,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_response(group)


@router.get("/groups/{group_id}", response_model=GroupResponse)
def get_group(group_id: str, service: GroupService = Depends(get_group_service)) -> GroupResponse:
    try:
        group = service.get_group(group_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_response(group)


@router.get("/users/{user_id}/groups", response_model=list[GroupResponse])
def get_groups_by_creator(
    user_id: str, service: GroupService = Depends(get_group_service)
) -> list[GroupResponse]:
    groups = service.get_groups_by_creator(user_id)
    return [_to_response(group) for group in groups]


@router.patch("/groups/{group_id}", response_model=GroupResponse)
def update_group(
    group_id: str, payload: GroupUpdateRequest, service: GroupService = Depends(get_group_service)
) -> GroupResponse:
    try:
        group = service.update_group(
            group_id,
            group_name=payload.groupName,
            group_desc=payload.groupDesc,
            group_icon_url=payload.groupIconUrl,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_response(group)


@router.patch("/groups/{group_id}/status", response_model=GroupResponse)
def update_group_status(
    group_id: str,
    payload: GroupStatusUpdateRequest,
    service: GroupService = Depends(get_group_service),
) -> GroupResponse:
    try:
        group = service.set_status(group_id, payload.groupStatus)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_response(group)
```

- [ ] **Step 10: Register the router in `app/main.py`**

```python
from fastapi import FastAPI

from app.api.v1.groups import router as groups_router
from app.api.v1.users import router as users_router

app = FastAPI(title="TaskNest", version="1.0.0")

app.include_router(users_router)
app.include_router(groups_router)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 11: Extend `tests/conftest.py` to share User + Group state**

```python
import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_group_service, get_user_service
from app.main import app
from app.repositories.group_repository import InMemoryGroupRepository
from app.repositories.user_repository import InMemoryUserRepository
from app.services.group_service import GroupService
from app.services.user_service import UserService


@pytest.fixture
def client():
    user_repo = InMemoryUserRepository()
    group_repo = InMemoryGroupRepository()

    user_service = UserService(user_repo)
    group_service = GroupService(group_repo, user_service)

    app.dependency_overrides[get_user_service] = lambda: user_service
    app.dependency_overrides[get_group_service] = lambda: group_service

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
```

- [ ] **Step 12: Write the failing integration test** `tests/integration/test_groups_api.py`

```python
def _create_user(client, first_name="Ada", last_name="Lovelace"):
    response = client.post("/api/v1/users", json={"firstName": first_name, "lastName": last_name})
    return response.json()["userId"]


def test_create_group_for_unknown_creator_returns_404(client):
    response = client.post(
        "/api/v1/groups",
        json={"groupName": "Smiths", "groupCategory": "Family", "groupCreaterId": "unknown"},
    )
    assert response.status_code == 404


def test_create_and_fetch_group(client):
    creator_id = _create_user(client)
    create_response = client.post(
        "/api/v1/groups",
        json={
            "groupName": "Smiths",
            "groupDesc": "Family group",
            "groupCategory": "Family",
            "groupCreaterId": creator_id,
        },
    )
    assert create_response.status_code == 201
    group_id = create_response.json()["groupId"]

    fetch_response = client.get(f"/api/v1/groups/{group_id}")
    assert fetch_response.status_code == 200
    assert fetch_response.json()["groupCreaterId"] == creator_id


def test_get_groups_by_creator(client):
    creator_id = _create_user(client)
    client.post(
        "/api/v1/groups",
        json={"groupName": "Smiths", "groupCategory": "Family", "groupCreaterId": creator_id},
    )

    response = client.get(f"/api/v1/users/{creator_id}/groups")
    assert response.status_code == 200
    groups = response.json()
    assert len(groups) == 1
    assert groups[0]["groupName"] == "Smiths"


def test_update_group_ignores_category_field(client):
    creator_id = _create_user(client)
    group_id = client.post(
        "/api/v1/groups",
        json={"groupName": "Smiths", "groupCategory": "Family", "groupCreaterId": creator_id},
    ).json()["groupId"]

    response = client.patch(f"/api/v1/groups/{group_id}", json={"groupName": "The Smiths"})
    assert response.status_code == 200
    body = response.json()
    assert body["groupName"] == "The Smiths"
    assert body["groupCategory"] == "Family"


def test_update_group_status(client):
    creator_id = _create_user(client)
    group_id = client.post(
        "/api/v1/groups",
        json={"groupName": "Smiths", "groupCategory": "Family", "groupCreaterId": creator_id},
    ).json()["groupId"]

    response = client.patch(f"/api/v1/groups/{group_id}/status", json={"groupStatus": "IN-ACTIVE"})
    assert response.status_code == 200
    assert response.json()["groupStatus"] == "IN-ACTIVE"
```

- [ ] **Step 13: Run the integration tests, then the full suite**

Run: `pytest tests/integration/test_groups_api.py -v`
Expected: `PASS` (5 passed)

Run: `pytest -v`
Expected: all tests pass.

- [ ] **Step 14: Commit**

```bash
git add app tests
git commit -m "feat: add Group entity CRUD with creator validation"
```

---

## Task 4: User-Group Relationship (Model, Repository, Service, Schema, Router)

**Files:**
- Create: `app/models/user_group.py`
- Create: `app/repositories/user_group_repository.py`
- Create: `app/services/user_group_service.py`
- Create: `app/schemas/user_group.py`
- Create: `app/api/v1/user_group.py`
- Modify: `app/dependencies.py` (add user-group providers)
- Modify: `app/main.py` (register user-group router)
- Modify: `tests/conftest.py` (wire user-group service override)
- Test: `tests/unit/test_user_group_service.py`
- Test: `tests/integration/test_user_group_api.py`

**Interfaces:**
- Consumes: `UserService.get_user` (Task 2), `GroupService.get_group` (Task 3), `NotFoundError` (Task 1).
- Produces: `UserGroupRelationship` domain model (`app/models/user_group.py`).
- Produces: `UserGroupService(repository, user_service, group_service)` with methods `associate(user_id: str, group_id: str, relationship: str) -> UserGroupRelationship`, `disassociate(user_id: str, group_id: str) -> None` (raises `NotFoundError` if no such association exists), `list_by_group(group_id: str) -> list[UserGroupRelationship]` — this last method is exposed for potential reuse but not required by the spec's endpoint list.
- Produces: `get_user_group_service() -> UserGroupService` in `app/dependencies.py`.

- [ ] **Step 1: Write the domain model** `app/models/user_group.py`

```python
from pydantic import BaseModel


class UserGroupRelationship(BaseModel):
    uuid: str
    groupId: str
    userId: str
    relationship: str
```

- [ ] **Step 2: Write the repository** `app/repositories/user_group_repository.py`

```python
from typing import Optional

from app.models.user_group import UserGroupRelationship
from app.repositories.base import BaseRepository


class InMemoryUserGroupRepository(BaseRepository[UserGroupRelationship]):
    def __init__(self) -> None:
        self._store: dict[str, UserGroupRelationship] = {}

    def add(self, entity: UserGroupRelationship) -> UserGroupRelationship:
        self._store[entity.uuid] = entity
        return entity

    def get(self, entity_id: str) -> Optional[UserGroupRelationship]:
        return self._store.get(entity_id)

    def update(self, entity: UserGroupRelationship) -> UserGroupRelationship:
        self._store[entity.uuid] = entity
        return entity

    def list_all(self) -> list[UserGroupRelationship]:
        return list(self._store.values())

    def find_by_user_and_group(
        self, user_id: str, group_id: str
    ) -> Optional[UserGroupRelationship]:
        for relationship in self._store.values():
            if relationship.userId == user_id and relationship.groupId == group_id:
                return relationship
        return None

    def delete(self, entity_id: str) -> None:
        self._store.pop(entity_id, None)

    def list_by_group(self, group_id: str) -> list[UserGroupRelationship]:
        return [r for r in self._store.values() if r.groupId == group_id]
```

- [ ] **Step 3: Write the failing unit test** `tests/unit/test_user_group_service.py`

```python
import pytest

from app.exceptions import NotFoundError
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


def test_associate_creates_relationship(user_group_service: UserGroupService, group_service, user_service):
    user, group = _make_user_and_group(user_service, group_service)
    relationship = user_group_service.associate(user.userId, group.groupId, "Father")
    assert relationship.uuid
    assert relationship.userId == user.userId
    assert relationship.groupId == group.groupId
    assert relationship.relationship == "Father"


def test_disassociate_removes_relationship(user_group_service: UserGroupService, group_service, user_service):
    user, group = _make_user_and_group(user_service, group_service)
    user_group_service.associate(user.userId, group.groupId, "Father")
    user_group_service.disassociate(user.userId, group.groupId)
    assert user_group_service.list_by_group(group.groupId) == []


def test_disassociate_raises_if_not_associated(user_group_service: UserGroupService, group_service, user_service):
    _, group = _make_user_and_group(user_service, group_service)
    user2 = user_service.create_user(first_name="Bob", last_name="Smith")
    with pytest.raises(NotFoundError):
        user_group_service.disassociate(user2.userId, group.groupId)
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `pytest tests/unit/test_user_group_service.py -v`
Expected: `FAIL` — `ModuleNotFoundError: No module named 'app.services.user_group_service'`

- [ ] **Step 5: Write the service** `app/services/user_group_service.py`

```python
import uuid

from app.exceptions import NotFoundError
from app.models.user_group import UserGroupRelationship
from app.repositories.user_group_repository import InMemoryUserGroupRepository
from app.services.group_service import GroupService
from app.services.user_service import UserService


class UserGroupService:
    def __init__(
        self,
        repository: InMemoryUserGroupRepository,
        user_service: UserService,
        group_service: GroupService,
    ):
        self._repository = repository
        self._user_service = user_service
        self._group_service = group_service

    def associate(self, user_id: str, group_id: str, relationship: str) -> UserGroupRelationship:
        self._user_service.get_user(user_id)
        self._group_service.get_group(group_id)
        entity = UserGroupRelationship(
            uuid=str(uuid.uuid4()), groupId=group_id, userId=user_id, relationship=relationship
        )
        return self._repository.add(entity)

    def disassociate(self, user_id: str, group_id: str) -> None:
        existing = self._repository.find_by_user_and_group(user_id, group_id)
        if existing is None:
            raise NotFoundError(f"User {user_id} is not associated with group {group_id}")
        self._repository.delete(existing.uuid)

    def list_by_group(self, group_id: str) -> list[UserGroupRelationship]:
        return self._repository.list_by_group(group_id)
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `pytest tests/unit/test_user_group_service.py -v`
Expected: `PASS` (5 passed)

- [ ] **Step 7: Write the schemas** `app/schemas/user_group.py`

```python
from pydantic import BaseModel


class UserGroupAssociateRequest(BaseModel):
    userId: str
    relationship: str


class UserGroupResponse(BaseModel):
    uuid: str
    groupId: str
    userId: str
    relationship: str
```

- [ ] **Step 8: Extend `app/dependencies.py`**

```python
from functools import lru_cache

from app.repositories.group_repository import InMemoryGroupRepository
from app.repositories.user_group_repository import InMemoryUserGroupRepository
from app.repositories.user_repository import InMemoryUserRepository
from app.services.group_service import GroupService
from app.services.user_group_service import UserGroupService
from app.services.user_service import UserService


@lru_cache
def get_user_repository() -> InMemoryUserRepository:
    return InMemoryUserRepository()


def get_user_service() -> UserService:
    return UserService(get_user_repository())


@lru_cache
def get_group_repository() -> InMemoryGroupRepository:
    return InMemoryGroupRepository()


def get_group_service() -> GroupService:
    return GroupService(get_group_repository(), get_user_service())


@lru_cache
def get_user_group_repository() -> InMemoryUserGroupRepository:
    return InMemoryUserGroupRepository()


def get_user_group_service() -> UserGroupService:
    return UserGroupService(get_user_group_repository(), get_user_service(), get_group_service())
```

- [ ] **Step 9: Write the router** `app/api/v1/user_group.py`

```python
from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_user_group_service
from app.exceptions import NotFoundError
from app.schemas.user_group import UserGroupAssociateRequest, UserGroupResponse
from app.services.user_group_service import UserGroupService

router = APIRouter(prefix="/api/v1/groups", tags=["user-group"])


@router.post(
    "/{group_id}/members", response_model=UserGroupResponse, status_code=status.HTTP_201_CREATED
)
def associate_user(
    group_id: str,
    payload: UserGroupAssociateRequest,
    service: UserGroupService = Depends(get_user_group_service),
) -> UserGroupResponse:
    try:
        relationship = service.associate(payload.userId, group_id, payload.relationship)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return UserGroupResponse(**relationship.model_dump())


@router.delete("/{group_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def disassociate_user(
    group_id: str, user_id: str, service: UserGroupService = Depends(get_user_group_service)
) -> None:
    try:
        service.disassociate(user_id, group_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
```

- [ ] **Step 10: Register the router in `app/main.py`**

```python
from fastapi import FastAPI

from app.api.v1.groups import router as groups_router
from app.api.v1.user_group import router as user_group_router
from app.api.v1.users import router as users_router

app = FastAPI(title="TaskNest", version="1.0.0")

app.include_router(users_router)
app.include_router(groups_router)
app.include_router(user_group_router)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 11: Extend `tests/conftest.py`**

```python
import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_group_service, get_user_group_service, get_user_service
from app.main import app
from app.repositories.group_repository import InMemoryGroupRepository
from app.repositories.user_group_repository import InMemoryUserGroupRepository
from app.repositories.user_repository import InMemoryUserRepository
from app.services.group_service import GroupService
from app.services.user_group_service import UserGroupService
from app.services.user_service import UserService


@pytest.fixture
def client():
    user_repo = InMemoryUserRepository()
    group_repo = InMemoryGroupRepository()
    user_group_repo = InMemoryUserGroupRepository()

    user_service = UserService(user_repo)
    group_service = GroupService(group_repo, user_service)
    user_group_service = UserGroupService(user_group_repo, user_service, group_service)

    app.dependency_overrides[get_user_service] = lambda: user_service
    app.dependency_overrides[get_group_service] = lambda: group_service
    app.dependency_overrides[get_user_group_service] = lambda: user_group_service

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
```

- [ ] **Step 12: Write the failing integration test** `tests/integration/test_user_group_api.py`

```python
def _create_user(client, first_name="Ada", last_name="Lovelace"):
    return client.post(
        "/api/v1/users", json={"firstName": first_name, "lastName": last_name}
    ).json()["userId"]


def _create_group(client, creator_id):
    return client.post(
        "/api/v1/groups",
        json={"groupName": "Smiths", "groupCategory": "Family", "groupCreaterId": creator_id},
    ).json()["groupId"]


def test_associate_user_to_group(client):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)

    response = client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": creator_id, "relationship": "Father"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["userId"] == creator_id
    assert body["groupId"] == group_id
    assert body["relationship"] == "Father"


def test_associate_unknown_user_returns_404(client):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)

    response = client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": "unknown", "relationship": "Father"}
    )
    assert response.status_code == 404


def test_disassociate_user_from_group(client):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)
    client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": creator_id, "relationship": "Father"}
    )

    response = client.delete(f"/api/v1/groups/{group_id}/members/{creator_id}")
    assert response.status_code == 204


def test_disassociate_unknown_association_returns_404(client):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)

    response = client.delete(f"/api/v1/groups/{group_id}/members/{creator_id}")
    assert response.status_code == 404
```

- [ ] **Step 13: Run the integration tests, then the full suite**

Run: `pytest tests/integration/test_user_group_api.py -v`
Expected: `PASS` (4 passed)

Run: `pytest -v`
Expected: all tests pass.

- [ ] **Step 14: Commit**

```bash
git add app tests
git commit -m "feat: add User-Group relationship associate/disassociate endpoints"
```

---

## Task 5: Task Entity (Model, Repository, Service, Schema, Router)

**Files:**
- Create: `app/models/task.py`
- Create: `app/repositories/task_repository.py`
- Create: `app/services/task_service.py`
- Create: `app/schemas/task.py`
- Create: `app/api/v1/tasks.py`
- Modify: `app/dependencies.py` (add task providers)
- Modify: `app/main.py` (register tasks router)
- Modify: `tests/conftest.py` (wire task service override)
- Test: `tests/unit/test_task_service.py`
- Test: `tests/integration/test_tasks_api.py`

**Interfaces:**
- Consumes: `TaskState` (Task 1), `UserService.get_user` (Task 2) — to validate `createdBy`/`updatedBy`.
- Produces: `Task` domain model (`app/models/task.py`) — consumed by Task 6.
- Produces: `TaskService(repository, user_service)` with methods `create_task(task_title, created_by, task_desc=None, task_due_date=None) -> Task`, `get_task(task_id: str) -> Task`, `update_task_meta(task_id, updated_by, task_title=None, task_desc=None) -> Task`, `update_task_state(task_id, updated_by, new_state: TaskState) -> Task`, `update_due_date(task_id, updated_by, due_date: datetime) -> Task` — consumed by Task 6's `TaskGroupService` for task-existence checks.
- Produces: `get_task_service() -> TaskService` in `app/dependencies.py`.

- [ ] **Step 1: Write the domain model** `app/models/task.py`

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
```

- [ ] **Step 2: Write the repository** `app/repositories/task_repository.py`

```python
from typing import Optional

from app.models.task import Task
from app.repositories.base import BaseRepository


class InMemoryTaskRepository(BaseRepository[Task]):
    def __init__(self) -> None:
        self._store: dict[str, Task] = {}

    def add(self, entity: Task) -> Task:
        self._store[entity.taskId] = entity
        return entity

    def get(self, entity_id: str) -> Optional[Task]:
        return self._store.get(entity_id)

    def update(self, entity: Task) -> Task:
        self._store[entity.taskId] = entity
        return entity

    def list_all(self) -> list[Task]:
        return list(self._store.values())
```

- [ ] **Step 3: Write the failing unit test** `tests/unit/test_task_service.py`

```python
from datetime import datetime, timedelta, timezone

import pytest

from app.exceptions import NotFoundError
from app.models.enums import TaskState
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


def test_create_task_requires_existing_user(task_service: TaskService):
    with pytest.raises(NotFoundError):
        task_service.create_task(task_title="Buy milk", created_by="unknown-user")


def test_create_task_defaults_to_todo(task_service: TaskService, user_service: UserService):
    user = user_service.create_user(first_name="Ada", last_name="Lovelace")
    task = task_service.create_task(task_title="Buy milk", created_by=user.userId)
    assert task.taskId
    assert task.taskState == TaskState.TODO
    assert task.createdBy == user.userId
    assert task.updatedAt is None
    assert task.updatedBy is None


def test_update_task_meta_changes_title_and_desc(task_service: TaskService, user_service: UserService):
    user = user_service.create_user(first_name="Ada", last_name="Lovelace")
    task = task_service.create_task(task_title="Buy milk", created_by=user.userId)
    updated = task_service.update_task_meta(
        task.taskId, updated_by=user.userId, task_title="Buy oat milk", task_desc="2 liters"
    )
    assert updated.taskTitle == "Buy oat milk"
    assert updated.taskDesc == "2 liters"
    assert updated.updatedBy == user.userId


def test_update_task_state_transitions(task_service: TaskService, user_service: UserService):
    user = user_service.create_user(first_name="Ada", last_name="Lovelace")
    task = task_service.create_task(task_title="Buy milk", created_by=user.userId)
    updated = task_service.update_task_state(
        task.taskId, updated_by=user.userId, new_state=TaskState.IN_PROGRESS
    )
    assert updated.taskState == TaskState.IN_PROGRESS


def test_update_due_date(task_service: TaskService, user_service: UserService):
    user = user_service.create_user(first_name="Ada", last_name="Lovelace")
    task = task_service.create_task(task_title="Buy milk", created_by=user.userId)
    new_due_date = datetime.now(timezone.utc) + timedelta(days=3)
    updated = task_service.update_due_date(task.taskId, updated_by=user.userId, due_date=new_due_date)
    assert updated.taskDueDate == new_due_date


def test_get_task_raises_not_found(task_service: TaskService):
    with pytest.raises(NotFoundError):
        task_service.get_task("unknown-task")
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `pytest tests/unit/test_task_service.py -v`
Expected: `FAIL` — `ModuleNotFoundError: No module named 'app.services.task_service'`

- [ ] **Step 5: Write the service** `app/services/task_service.py`

```python
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.exceptions import NotFoundError
from app.models.enums import TaskState
from app.models.task import Task
from app.repositories.base import BaseRepository
from app.services.user_service import UserService


class TaskService:
    def __init__(self, repository: BaseRepository[Task], user_service: UserService):
        self._repository = repository
        self._user_service = user_service

    def create_task(
        self,
        task_title: str,
        created_by: str,
        task_desc: Optional[str] = None,
        task_due_date: Optional[datetime] = None,
    ) -> Task:
        self._user_service.get_user(created_by)
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
        )
        return self._repository.add(task)

    def get_task(self, task_id: str) -> Task:
        task = self._repository.get(task_id)
        if task is None:
            raise NotFoundError(f"Task {task_id} not found")
        return task

    def update_task_meta(
        self,
        task_id: str,
        updated_by: str,
        task_title: Optional[str] = None,
        task_desc: Optional[str] = None,
    ) -> Task:
        self._user_service.get_user(updated_by)
        task = self.get_task(task_id)
        updated = task.model_copy(
            update={
                "taskTitle": task_title if task_title is not None else task.taskTitle,
                "taskDesc": task_desc if task_desc is not None else task.taskDesc,
                "updatedBy": updated_by,
                "updatedAt": datetime.now(timezone.utc),
            }
        )
        return self._repository.update(updated)

    def update_task_state(self, task_id: str, updated_by: str, new_state: TaskState) -> Task:
        self._user_service.get_user(updated_by)
        task = self.get_task(task_id)
        updated = task.model_copy(
            update={
                "taskState": new_state,
                "updatedBy": updated_by,
                "updatedAt": datetime.now(timezone.utc),
            }
        )
        return self._repository.update(updated)

    def update_due_date(self, task_id: str, updated_by: str, due_date: datetime) -> Task:
        self._user_service.get_user(updated_by)
        task = self.get_task(task_id)
        updated = task.model_copy(
            update={
                "taskDueDate": due_date,
                "updatedBy": updated_by,
                "updatedAt": datetime.now(timezone.utc),
            }
        )
        return self._repository.update(updated)
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `pytest tests/unit/test_task_service.py -v`
Expected: `PASS` (6 passed)

- [ ] **Step 7: Write the schemas** `app/schemas/task.py`

```python
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.enums import TaskState


class TaskCreateRequest(BaseModel):
    taskTitle: str
    createdBy: str
    taskDesc: Optional[str] = None
    taskDueDate: Optional[datetime] = None


class TaskMetaUpdateRequest(BaseModel):
    updatedBy: str
    taskTitle: Optional[str] = None
    taskDesc: Optional[str] = None


class TaskStateUpdateRequest(BaseModel):
    updatedBy: str
    taskState: TaskState


class TaskDueDateUpdateRequest(BaseModel):
    updatedBy: str
    taskDueDate: datetime


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
```

- [ ] **Step 8: Extend `app/dependencies.py`**

```python
from functools import lru_cache

from app.repositories.group_repository import InMemoryGroupRepository
from app.repositories.task_repository import InMemoryTaskRepository
from app.repositories.user_group_repository import InMemoryUserGroupRepository
from app.repositories.user_repository import InMemoryUserRepository
from app.services.group_service import GroupService
from app.services.task_service import TaskService
from app.services.user_group_service import UserGroupService
from app.services.user_service import UserService


@lru_cache
def get_user_repository() -> InMemoryUserRepository:
    return InMemoryUserRepository()


def get_user_service() -> UserService:
    return UserService(get_user_repository())


@lru_cache
def get_group_repository() -> InMemoryGroupRepository:
    return InMemoryGroupRepository()


def get_group_service() -> GroupService:
    return GroupService(get_group_repository(), get_user_service())


@lru_cache
def get_user_group_repository() -> InMemoryUserGroupRepository:
    return InMemoryUserGroupRepository()


def get_user_group_service() -> UserGroupService:
    return UserGroupService(get_user_group_repository(), get_user_service(), get_group_service())


@lru_cache
def get_task_repository() -> InMemoryTaskRepository:
    return InMemoryTaskRepository()


def get_task_service() -> TaskService:
    return TaskService(get_task_repository(), get_user_service())
```

- [ ] **Step 9: Write the router** `app/api/v1/tasks.py`

```python
from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_task_service
from app.exceptions import NotFoundError
from app.models.task import Task
from app.schemas.task import (
    TaskCreateRequest,
    TaskDueDateUpdateRequest,
    TaskMetaUpdateRequest,
    TaskResponse,
    TaskStateUpdateRequest,
)
from app.services.task_service import TaskService

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


def _to_response(task: Task) -> TaskResponse:
    return TaskResponse(**task.model_dump())


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreateRequest, service: TaskService = Depends(get_task_service)
) -> TaskResponse:
    try:
        task = service.create_task(
            task_title=payload.taskTitle,
            created_by=payload.createdBy,
            task_desc=payload.taskDesc,
            task_due_date=payload.taskDueDate,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_response(task)


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: str, service: TaskService = Depends(get_task_service)) -> TaskResponse:
    try:
        task = service.get_task(task_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_response(task)


@router.patch("/{task_id}", response_model=TaskResponse)
def update_task_meta(
    task_id: str, payload: TaskMetaUpdateRequest, service: TaskService = Depends(get_task_service)
) -> TaskResponse:
    try:
        task = service.update_task_meta(
            task_id,
            updated_by=payload.updatedBy,
            task_title=payload.taskTitle,
            task_desc=payload.taskDesc,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_response(task)


@router.patch("/{task_id}/state", response_model=TaskResponse)
def update_task_state(
    task_id: str, payload: TaskStateUpdateRequest, service: TaskService = Depends(get_task_service)
) -> TaskResponse:
    try:
        task = service.update_task_state(task_id, updated_by=payload.updatedBy, new_state=payload.taskState)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_response(task)


@router.patch("/{task_id}/due-date", response_model=TaskResponse)
def update_due_date(
    task_id: str, payload: TaskDueDateUpdateRequest, service: TaskService = Depends(get_task_service)
) -> TaskResponse:
    try:
        task = service.update_due_date(task_id, updated_by=payload.updatedBy, due_date=payload.taskDueDate)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_response(task)
```

- [ ] **Step 10: Register the router in `app/main.py`**

```python
from fastapi import FastAPI

from app.api.v1.groups import router as groups_router
from app.api.v1.tasks import router as tasks_router
from app.api.v1.user_group import router as user_group_router
from app.api.v1.users import router as users_router

app = FastAPI(title="TaskNest", version="1.0.0")

app.include_router(users_router)
app.include_router(groups_router)
app.include_router(user_group_router)
app.include_router(tasks_router)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 11: Extend `tests/conftest.py`**

```python
import pytest
from fastapi.testclient import TestClient

from app.dependencies import (
    get_group_service,
    get_task_service,
    get_user_group_service,
    get_user_service,
)
from app.main import app
from app.repositories.group_repository import InMemoryGroupRepository
from app.repositories.task_repository import InMemoryTaskRepository
from app.repositories.user_group_repository import InMemoryUserGroupRepository
from app.repositories.user_repository import InMemoryUserRepository
from app.services.group_service import GroupService
from app.services.task_service import TaskService
from app.services.user_group_service import UserGroupService
from app.services.user_service import UserService


@pytest.fixture
def client():
    user_repo = InMemoryUserRepository()
    group_repo = InMemoryGroupRepository()
    user_group_repo = InMemoryUserGroupRepository()
    task_repo = InMemoryTaskRepository()

    user_service = UserService(user_repo)
    group_service = GroupService(group_repo, user_service)
    user_group_service = UserGroupService(user_group_repo, user_service, group_service)
    task_service = TaskService(task_repo, user_service)

    app.dependency_overrides[get_user_service] = lambda: user_service
    app.dependency_overrides[get_group_service] = lambda: group_service
    app.dependency_overrides[get_user_group_service] = lambda: user_group_service
    app.dependency_overrides[get_task_service] = lambda: task_service

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
```

- [ ] **Step 12: Write the failing integration test** `tests/integration/test_tasks_api.py`

```python
def _create_user(client, first_name="Ada", last_name="Lovelace"):
    return client.post(
        "/api/v1/users", json={"firstName": first_name, "lastName": last_name}
    ).json()["userId"]


def test_create_and_fetch_task(client):
    user_id = _create_user(client)
    create_response = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": user_id}
    )
    assert create_response.status_code == 201
    body = create_response.json()
    assert body["taskState"] == "TODO"
    task_id = body["taskId"]

    fetch_response = client.get(f"/api/v1/tasks/{task_id}")
    assert fetch_response.status_code == 200
    assert fetch_response.json()["taskId"] == task_id


def test_create_task_unknown_user_returns_404(client):
    response = client.post("/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": "unknown"})
    assert response.status_code == 404


def test_update_task_meta(client):
    user_id = _create_user(client)
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": user_id}
    ).json()["taskId"]

    response = client.patch(
        f"/api/v1/tasks/{task_id}", json={"updatedBy": user_id, "taskTitle": "Buy oat milk"}
    )
    assert response.status_code == 200
    assert response.json()["taskTitle"] == "Buy oat milk"


def test_update_task_state(client):
    user_id = _create_user(client)
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": user_id}
    ).json()["taskId"]

    response = client.patch(
        f"/api/v1/tasks/{task_id}/state", json={"updatedBy": user_id, "taskState": "IN-PROGRESS"}
    )
    assert response.status_code == 200
    assert response.json()["taskState"] == "IN-PROGRESS"


def test_update_task_due_date(client):
    user_id = _create_user(client)
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": user_id}
    ).json()["taskId"]

    response = client.patch(
        f"/api/v1/tasks/{task_id}/due-date",
        json={"updatedBy": user_id, "taskDueDate": "2026-08-01T00:00:00Z"},
    )
    assert response.status_code == 200
    assert response.json()["taskDueDate"].startswith("2026-08-01")
```

- [ ] **Step 13: Run the integration tests, then the full suite**

Run: `pytest tests/integration/test_tasks_api.py -v`
Expected: `PASS` (5 passed)

Run: `pytest -v`
Expected: all tests pass.

- [ ] **Step 14: Commit**

```bash
git add app tests
git commit -m "feat: add Task entity CRUD with state and due-date updates"
```

---

## Task 6: Task-Group Relationship (Model, Repository, Service, Schema, Router)

**Files:**
- Create: `app/models/task_group.py`
- Create: `app/repositories/task_group_repository.py`
- Create: `app/services/task_group_service.py`
- Create: `app/schemas/task_group.py`
- Create: `app/api/v1/task_group.py`
- Modify: `app/dependencies.py` (add task-group providers — final version)
- Modify: `app/main.py` (register task-group router — final version)
- Modify: `tests/conftest.py` (wire task-group service override — final version)
- Test: `tests/unit/test_task_group_service.py`
- Test: `tests/integration/test_task_group_api.py`

**Interfaces:**
- Consumes: `TaskService.get_task` (Task 5), `GroupService.get_group` (Task 3), `UserService.get_user` (Task 2), `NotFoundError` (Task 1).
- Produces: `TaskGroupRelationship` domain model (`app/models/task_group.py`).
- Produces: `TaskGroupService(repository, task_service, group_service, user_service)` with methods `assign(task_id: str, group_id: str, assignee_id: str) -> TaskGroupRelationship` (creates the link if none exists for the `(task_id, group_id)` pair, or updates the existing link's `assigneeId` if one does), `unassign(task_id: str, group_id: str, assignee_id: str) -> TaskGroupRelationship` (raises `NotFoundError` if no link exists for that exact `(task_id, group_id, assigneeId)` triple; otherwise sets `assigneeId` back to `None`).
- Produces: `get_task_group_service() -> TaskGroupService` in `app/dependencies.py`.

- [ ] **Step 1: Write the domain model** `app/models/task_group.py`

```python
from typing import Optional

from pydantic import BaseModel


class TaskGroupRelationship(BaseModel):
    uuid: str
    taskId: str
    groupId: str
    assigneeId: Optional[str] = None
```

- [ ] **Step 2: Write the repository** `app/repositories/task_group_repository.py`

```python
from typing import Optional

from app.models.task_group import TaskGroupRelationship
from app.repositories.base import BaseRepository


class InMemoryTaskGroupRepository(BaseRepository[TaskGroupRelationship]):
    def __init__(self) -> None:
        self._store: dict[str, TaskGroupRelationship] = {}

    def add(self, entity: TaskGroupRelationship) -> TaskGroupRelationship:
        self._store[entity.uuid] = entity
        return entity

    def get(self, entity_id: str) -> Optional[TaskGroupRelationship]:
        return self._store.get(entity_id)

    def update(self, entity: TaskGroupRelationship) -> TaskGroupRelationship:
        self._store[entity.uuid] = entity
        return entity

    def list_all(self) -> list[TaskGroupRelationship]:
        return list(self._store.values())

    def find_by_task_and_group(
        self, task_id: str, group_id: str
    ) -> Optional[TaskGroupRelationship]:
        for relationship in self._store.values():
            if relationship.taskId == task_id and relationship.groupId == group_id:
                return relationship
        return None
```

- [ ] **Step 3: Write the failing unit test** `tests/unit/test_task_group_service.py`

```python
import pytest

from app.exceptions import NotFoundError
from app.repositories.group_repository import InMemoryGroupRepository
from app.repositories.task_group_repository import InMemoryTaskGroupRepository
from app.repositories.task_repository import InMemoryTaskRepository
from app.repositories.user_repository import InMemoryUserRepository
from app.services.group_service import GroupService
from app.services.task_group_service import TaskGroupService
from app.services.task_service import TaskService
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
def task_group_service(
    task_service: TaskService, group_service: GroupService, user_service: UserService
) -> TaskGroupService:
    return TaskGroupService(InMemoryTaskGroupRepository(), task_service, group_service, user_service)


def _setup(user_service, group_service, task_service):
    creator = user_service.create_user(first_name="Ada", last_name="Lovelace")
    assignee = user_service.create_user(first_name="Bob", last_name="Smith")
    group = group_service.create_group(
        group_name="Smiths", group_desc=None, group_category="Family", creater_id=creator.userId
    )
    task = task_service.create_task(task_title="Buy milk", created_by=creator.userId)
    return creator, assignee, group, task


def test_assign_raises_if_task_missing(task_group_service, user_service, group_service, task_service):
    _, assignee, group, _ = _setup(user_service, group_service, task_service)
    with pytest.raises(NotFoundError):
        task_group_service.assign("unknown-task", group.groupId, assignee.userId)


def test_assign_raises_if_group_missing(task_group_service, user_service, group_service, task_service):
    _, assignee, _, task = _setup(user_service, group_service, task_service)
    with pytest.raises(NotFoundError):
        task_group_service.assign(task.taskId, "unknown-group", assignee.userId)


def test_assign_raises_if_assignee_missing(task_group_service, user_service, group_service, task_service):
    _, _, group, task = _setup(user_service, group_service, task_service)
    with pytest.raises(NotFoundError):
        task_group_service.assign(task.taskId, group.groupId, "unknown-user")


def test_assign_creates_relationship(task_group_service, user_service, group_service, task_service):
    _, assignee, group, task = _setup(user_service, group_service, task_service)
    relationship = task_group_service.assign(task.taskId, group.groupId, assignee.userId)
    assert relationship.uuid
    assert relationship.taskId == task.taskId
    assert relationship.groupId == group.groupId
    assert relationship.assigneeId == assignee.userId


def test_assign_twice_updates_existing_relationship(
    task_group_service, user_service, group_service, task_service
):
    creator, assignee, group, task = _setup(user_service, group_service, task_service)
    first = task_group_service.assign(task.taskId, group.groupId, assignee.userId)
    second = task_group_service.assign(task.taskId, group.groupId, creator.userId)
    assert first.uuid == second.uuid
    assert second.assigneeId == creator.userId


def test_unassign_clears_assignee(task_group_service, user_service, group_service, task_service):
    _, assignee, group, task = _setup(user_service, group_service, task_service)
    task_group_service.assign(task.taskId, group.groupId, assignee.userId)
    result = task_group_service.unassign(task.taskId, group.groupId, assignee.userId)
    assert result.assigneeId is None


def test_unassign_raises_if_no_matching_assignment(
    task_group_service, user_service, group_service, task_service
):
    _, assignee, group, task = _setup(user_service, group_service, task_service)
    with pytest.raises(NotFoundError):
        task_group_service.unassign(task.taskId, group.groupId, assignee.userId)
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `pytest tests/unit/test_task_group_service.py -v`
Expected: `FAIL` — `ModuleNotFoundError: No module named 'app.services.task_group_service'`

- [ ] **Step 5: Write the service** `app/services/task_group_service.py`

```python
import uuid

from app.exceptions import NotFoundError
from app.models.task_group import TaskGroupRelationship
from app.repositories.task_group_repository import InMemoryTaskGroupRepository
from app.services.group_service import GroupService
from app.services.task_service import TaskService
from app.services.user_service import UserService


class TaskGroupService:
    def __init__(
        self,
        repository: InMemoryTaskGroupRepository,
        task_service: TaskService,
        group_service: GroupService,
        user_service: UserService,
    ):
        self._repository = repository
        self._task_service = task_service
        self._group_service = group_service
        self._user_service = user_service

    def assign(self, task_id: str, group_id: str, assignee_id: str) -> TaskGroupRelationship:
        self._task_service.get_task(task_id)
        self._group_service.get_group(group_id)
        self._user_service.get_user(assignee_id)

        existing = self._repository.find_by_task_and_group(task_id, group_id)
        if existing is not None:
            updated = existing.model_copy(update={"assigneeId": assignee_id})
            return self._repository.update(updated)

        entity = TaskGroupRelationship(
            uuid=str(uuid.uuid4()), taskId=task_id, groupId=group_id, assigneeId=assignee_id
        )
        return self._repository.add(entity)

    def unassign(self, task_id: str, group_id: str, assignee_id: str) -> TaskGroupRelationship:
        existing = self._repository.find_by_task_and_group(task_id, group_id)
        if existing is None or existing.assigneeId != assignee_id:
            raise NotFoundError(
                f"No assignment of user {assignee_id} to task {task_id} in group {group_id}"
            )
        updated = existing.model_copy(update={"assigneeId": None})
        return self._repository.update(updated)
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `pytest tests/unit/test_task_group_service.py -v`
Expected: `PASS` (7 passed)

- [ ] **Step 7: Write the schemas** `app/schemas/task_group.py`

```python
from typing import Optional

from pydantic import BaseModel


class TaskGroupAssignRequest(BaseModel):
    assigneeId: str


class TaskGroupResponse(BaseModel):
    uuid: str
    taskId: str
    groupId: str
    assigneeId: Optional[str] = None
```

- [ ] **Step 8: Extend `app/dependencies.py` (final version)**

```python
from functools import lru_cache

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


@lru_cache
def get_user_repository() -> InMemoryUserRepository:
    return InMemoryUserRepository()


def get_user_service() -> UserService:
    return UserService(get_user_repository())


@lru_cache
def get_group_repository() -> InMemoryGroupRepository:
    return InMemoryGroupRepository()


def get_group_service() -> GroupService:
    return GroupService(get_group_repository(), get_user_service())


@lru_cache
def get_user_group_repository() -> InMemoryUserGroupRepository:
    return InMemoryUserGroupRepository()


def get_user_group_service() -> UserGroupService:
    return UserGroupService(get_user_group_repository(), get_user_service(), get_group_service())


@lru_cache
def get_task_repository() -> InMemoryTaskRepository:
    return InMemoryTaskRepository()


def get_task_service() -> TaskService:
    return TaskService(get_task_repository(), get_user_service())


@lru_cache
def get_task_group_repository() -> InMemoryTaskGroupRepository:
    return InMemoryTaskGroupRepository()


def get_task_group_service() -> TaskGroupService:
    return TaskGroupService(
        get_task_group_repository(), get_task_service(), get_group_service(), get_user_service()
    )
```

- [ ] **Step 9: Write the router** `app/api/v1/task_group.py`

```python
from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_task_group_service
from app.exceptions import NotFoundError
from app.schemas.task_group import TaskGroupAssignRequest, TaskGroupResponse
from app.services.task_group_service import TaskGroupService

router = APIRouter(prefix="/api/v1/groups/{group_id}/tasks/{task_id}/assignee", tags=["task-group"])


@router.post("", response_model=TaskGroupResponse, status_code=status.HTTP_201_CREATED)
def assign_task(
    group_id: str,
    task_id: str,
    payload: TaskGroupAssignRequest,
    service: TaskGroupService = Depends(get_task_group_service),
) -> TaskGroupResponse:
    try:
        relationship = service.assign(task_id, group_id, payload.assigneeId)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return TaskGroupResponse(**relationship.model_dump())


@router.delete("/{assignee_id}", response_model=TaskGroupResponse)
def unassign_task(
    group_id: str,
    task_id: str,
    assignee_id: str,
    service: TaskGroupService = Depends(get_task_group_service),
) -> TaskGroupResponse:
    try:
        relationship = service.unassign(task_id, group_id, assignee_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return TaskGroupResponse(**relationship.model_dump())
```

- [ ] **Step 10: Register the router in `app/main.py` (final version)**

```python
from fastapi import FastAPI

from app.api.v1.groups import router as groups_router
from app.api.v1.task_group import router as task_group_router
from app.api.v1.tasks import router as tasks_router
from app.api.v1.user_group import router as user_group_router
from app.api.v1.users import router as users_router

app = FastAPI(title="TaskNest", version="1.0.0")

app.include_router(users_router)
app.include_router(groups_router)
app.include_router(user_group_router)
app.include_router(tasks_router)
app.include_router(task_group_router)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 11: Extend `tests/conftest.py` (final version)**

```python
import pytest
from fastapi.testclient import TestClient

from app.dependencies import (
    get_group_service,
    get_task_group_service,
    get_task_service,
    get_user_group_service,
    get_user_service,
)
from app.main import app
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
def client():
    user_repo = InMemoryUserRepository()
    group_repo = InMemoryGroupRepository()
    user_group_repo = InMemoryUserGroupRepository()
    task_repo = InMemoryTaskRepository()
    task_group_repo = InMemoryTaskGroupRepository()

    user_service = UserService(user_repo)
    group_service = GroupService(group_repo, user_service)
    user_group_service = UserGroupService(user_group_repo, user_service, group_service)
    task_service = TaskService(task_repo, user_service)
    task_group_service = TaskGroupService(task_group_repo, task_service, group_service, user_service)

    app.dependency_overrides[get_user_service] = lambda: user_service
    app.dependency_overrides[get_group_service] = lambda: group_service
    app.dependency_overrides[get_user_group_service] = lambda: user_group_service
    app.dependency_overrides[get_task_service] = lambda: task_service
    app.dependency_overrides[get_task_group_service] = lambda: task_group_service

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
```

- [ ] **Step 12: Write the failing integration test** `tests/integration/test_task_group_api.py`

```python
def _create_user(client, first_name="Ada", last_name="Lovelace"):
    return client.post(
        "/api/v1/users", json={"firstName": first_name, "lastName": last_name}
    ).json()["userId"]


def _create_group(client, creator_id):
    return client.post(
        "/api/v1/groups",
        json={"groupName": "Smiths", "groupCategory": "Family", "groupCreaterId": creator_id},
    ).json()["groupId"]


def _create_task(client, creator_id):
    return client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": creator_id}
    ).json()["taskId"]


def test_assign_task_to_group_member(client):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)
    task_id = _create_task(client, creator_id)

    response = client.post(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": creator_id}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["taskId"] == task_id
    assert body["groupId"] == group_id
    assert body["assigneeId"] == creator_id


def test_assign_task_unknown_assignee_returns_404(client):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)
    task_id = _create_task(client, creator_id)

    response = client.post(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": "unknown"}
    )
    assert response.status_code == 404


def test_unassign_task(client):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)
    task_id = _create_task(client, creator_id)
    client.post(f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": creator_id})

    response = client.delete(f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee/{creator_id}")
    assert response.status_code == 200
    assert response.json()["assigneeId"] is None


def test_unassign_task_without_prior_assignment_returns_404(client):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)
    task_id = _create_task(client, creator_id)

    response = client.delete(f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee/{creator_id}")
    assert response.status_code == 404
```

- [ ] **Step 13: Run the integration tests, then the full suite**

Run: `pytest tests/integration/test_task_group_api.py -v`
Expected: `PASS` (4 passed)

Run: `pytest -v`
Expected: all tests pass (smoke + 5 unit files + 5 integration files).

- [ ] **Step 14: Commit**

```bash
git add app tests
git commit -m "feat: add Task-Group relationship assign/unassign endpoints"
```

---

## Task 7: Final Wiring Check, README, and Full-Suite Verification

**Files:**
- Create: `README.md`
- Modify: `Arch.md` (append final endpoint inventory)

**Interfaces:**
- Consumes: everything from Tasks 1–6 — this task adds no new code, only verifies the assembled system and documents it.

- [ ] **Step 1: Run the complete test suite with verbose output**

Run: `pytest -v`
Expected: all tests across `tests/test_app_smoke.py`, `tests/unit/*.py`, and `tests/integration/*.py` pass — 0 failures.

- [ ] **Step 2: Start the server and manually smoke-test one full flow**

Run:
```bash
uvicorn app.main:app --reload &
sleep 1
curl -s -X POST localhost:8000/api/v1/users -H 'Content-Type: application/json' \
  -d '{"firstName":"Ada","lastName":"Lovelace"}'
```
Expected: JSON body with a generated `userId` and `userStatus: "ACTIVE"`. Stop the server afterward: `kill %1`.

- [ ] **Step 3: Append the endpoint inventory to `Arch.md`**

Add this section to the end of `Arch.md`:

```markdown
## API Endpoint Inventory (v1)

| Method | Path | Purpose |
|---|---|---|
| POST | /api/v1/users | Create a user |
| GET | /api/v1/users/{userId} | Fetch a user |
| PATCH | /api/v1/users/{userId} | Update name/phone/email |
| PATCH | /api/v1/users/{userId}/status | Toggle ACTIVE/IN-ACTIVE |
| POST | /api/v1/groups | Create a group |
| GET | /api/v1/groups/{groupId} | Fetch a group |
| GET | /api/v1/users/{userId}/groups | Fetch groups created by a user |
| PATCH | /api/v1/groups/{groupId} | Update name/desc/iconUrl (not category) |
| PATCH | /api/v1/groups/{groupId}/status | Toggle ACTIVE/IN-ACTIVE |
| POST | /api/v1/groups/{groupId}/members | Associate a user to a group |
| DELETE | /api/v1/groups/{groupId}/members/{userId} | De-associate a user from a group |
| POST | /api/v1/tasks | Create a task |
| GET | /api/v1/tasks/{taskId} | Fetch a task |
| PATCH | /api/v1/tasks/{taskId} | Update title/desc |
| PATCH | /api/v1/tasks/{taskId}/state | Move task to a new state |
| PATCH | /api/v1/tasks/{taskId}/due-date | Update due date |
| POST | /api/v1/groups/{groupId}/tasks/{taskId}/assignee | Assign task to a user within a group |
| DELETE | /api/v1/groups/{groupId}/tasks/{taskId}/assignee/{assigneeId} | Remove that assignment |
```

- [ ] **Step 4: Write `README.md`**

```markdown
# TaskNest

Backend REST API for TaskNest — Users, Groups, Tasks, and their
relationships — built with FastAPI and in-memory storage.

## Setup

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

## Run

uvicorn app.main:app --reload

API docs (Swagger UI) at http://localhost:8000/docs

## Test

pytest -v

See `Arch.md` for architecture and the full endpoint inventory, and
`OpenPoints.md` for known gaps and deferred decisions.
```

- [ ] **Step 5: Commit**

```bash
git add Arch.md README.md
git commit -m "docs: add README and finalize architecture endpoint inventory"
```

---

## Verification (end-to-end)

1. `pytest -v` — all unit + integration tests across all five entities pass.
2. `uvicorn app.main:app --reload`, then visit `http://localhost:8000/docs` — Swagger UI lists all endpoints from the table in `Arch.md`, grouped by tag (`users`, `groups`, `user-group`, `tasks`, `task-group`).
3. Manually exercise the full cross-entity flow via `curl` or Swagger UI: create a user → create a group with that user as creator → associate a (possibly different) user to the group → create a task by the creator → assign the task to a group member → move the task through `TODO → IN-PROGRESS → COMPLETED` → unassign the task. Confirm each step returns the expected status code (`201`/`200`/`204`) and body shape.
4. Confirm `Arch.md` and `OpenPoints.md` exist at the repo root and reflect the finished system.
