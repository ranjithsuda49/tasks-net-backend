# TaskNest — Architecture

## Layers

1. **api/v1** — FastAPI routers. Only HTTP concerns: request parsing, status
   codes, translating domain exceptions to `HTTPException`. No business logic.
2. **services** — Business logic. Most services take `BaseRepository`
   abstractions in their constructor (constructor injection). A few
   (`GroupService`, `UserGroupService`, `TaskGroupService`) instead depend on
   the concrete `GroupRepository`/`UserGroupRepository`/`TaskGroupRepository`
   class because they need an entity-specific query method (e.g.
   `list_by_creator`, `find_by_user_and_group`) that isn't part of the
   generic `BaseRepository[T]` interface — see the SOLID mapping below for
   the same caveat.
3. **repositories** — `BaseRepository[T]` (abstract) defines `add`, `get`,
   `update`, `list_all`. Each entity has one Postgres-backed repository
   class (`UserRepository`, `GroupRepository`, `TaskRepository`,
   `UserGroupRepository`, `TaskGroupRepository`) implementing it via a
   SQLAlchemy `Session`, mapping Pydantic domain models to/from the ORM rows
   defined in `app/db/orm_models.py`. One repository per entity/relationship.
4. **models** — Domain entities (Pydantic models), the shape of truth held by
   repositories.
5. **schemas** — API request/response contracts (Pydantic models), decoupled
   from domain models so the wire format can evolve independently of the
   internal shape.

## Dependency Injection / Composition Root

`app/dependencies.py` is the only place that constructs concrete repository
and service instances. Repository providers build a repository per request
from a SQLAlchemy `Session` (`app/db/session.get_db_session`, itself a
`Depends`), so every repository used within one request shares one
`Session`/transaction, committed or rolled back atomically at the end of
the request. Services are built fresh per-request by composing the
per-request repositories via FastAPI's `Depends`.

Tests override the service-level provider functions (via
`app.dependency_overrides`) with a shared set of repositories/services per
test, each built from a transactional `db_session` fixture (`tests/conftest.py`)
that's rolled back at the end of the test — so tests never see state from
other tests and cross-entity integration tests (e.g. create a user, then a
group referencing it) still share consistent state within a single test.

## SOLID mapping

- **S**: routers, services, and repositories each have exactly one reason to
  change (HTTP shape, business rule, storage mechanism respectively).
- **O**: new repository implementations (e.g. a future `SqlUserRepository`)
  can be added without modifying `UserService`.
- **L**: any `BaseRepository[T]` implementation is substitutable wherever a
  service expects one — enforced by the shared abstract base.
- **I**: repository interfaces are per-entity rather than one large
  interface, so no repository is forced to implement methods it doesn't need.
- **D**: most services and routers depend on the `BaseRepository[T]`
  abstraction, injected via `Depends`. A few services (`GroupService`,
  `UserGroupService`, `TaskGroupService`) depend on a concrete repository
  type instead, because they need an entity-specific query method (e.g.
  `list_by_creator`, `find_by_user_and_group`) that isn't part of the
  generic `BaseRepository[T]` interface.

## Entity relationships

- `User` 1—0..N `UserGroupRelationship` N—1 `Group` (many-to-many join with
  a `relationship` label, e.g. "Father").
- `Task` 0..1—0..N `TaskGroupRelationship` N—0..1 `Group`, with an optional
  `assigneeId` (a `User`) on each join row.

## Request flow example (create user)

`POST /api/v1/users` → `api/v1/users.create_user` → `UserService.create_user`
(generates UUID4, timestamps, builds `User` domain model) →
`UserRepository.add` (inserts a row via SQLAlchemy) → router maps `User`
domain model to `UserResponse` schema → FastAPI serializes to JSON.

## Testing strategy

- **Unit tests** (`tests/unit/`) instantiate a service directly with a
  repository built from the shared transactional `db_session` fixture,
  bypassing HTTP entirely.
- **Integration tests** (`tests/integration/`) use FastAPI's `TestClient`
  against the real app with `app.dependency_overrides` pointed at
  repositories/services built from the same `db_session` fixture per test
  (see `tests/conftest.py`), exercising the full router → service →
  repository path against real Postgres.
- **Repository tests** (`tests/repositories/`) exercise each repository
  directly against real Postgres — `add`/`get`/`update`/`list_all` plus
  entity-specific extras, including unique-constraint violations and the
  `TaskGroupRepository.update()` "clears `assigneeId`, never deletes the
  row" guarantee.

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
| GET | /api/v1/groups/{groupId}/members | Fetch a group's members |
| DELETE | /api/v1/groups/{groupId}/members/{userId} | De-associate a user from a group |
| POST | /api/v1/tasks | Create a task |
| GET | /api/v1/tasks/{taskId} | Fetch a task |
| PATCH | /api/v1/tasks/{taskId} | Update title/desc |
| PATCH | /api/v1/tasks/{taskId}/state | Move task to a new state |
| PATCH | /api/v1/tasks/{taskId}/due-date | Update due date |
| POST | /api/v1/groups/{groupId}/tasks/{taskId}/assignee | Assign task to a user within a group |
| DELETE | /api/v1/groups/{groupId}/tasks/{taskId}/assignee/{assigneeId} | Remove that assignment |
