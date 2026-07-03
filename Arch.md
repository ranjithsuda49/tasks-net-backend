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
