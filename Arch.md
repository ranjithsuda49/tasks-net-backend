# TaskNest — Architecture

## Overview

TaskNest is a FastAPI backend for three entities — Users, Groups, and Tasks — plus two
many-to-many relationships between them (User↔Group membership, Task↔Group assignment).
Every write is authenticated via a Firebase ID token and authorized against ownership
rules enforced in the service layer. Persistence is entirely PostgreSQL via SQLAlchemy;
there is no in-memory or cached state anywhere, including in tests. See `requirements.md`
for the original spec and `OpenPoints.md` for known gaps, deferred decisions, and
clean-architecture follow-ups — check `OpenPoints.md` before treating something there as
an oversight to fix.

## Tech Stack

- **FastAPI** — HTTP layer, request validation (via Pydantic), OpenAPI generation.
- **Pydantic** — both domain models (`app/models/`) and API schemas (`app/schemas/`).
- **SQLAlchemy 2.x ORM** (`app/db/orm_models.py`) + **psycopg3** — persistence.
- **Alembic** (`migrations/`) — schema migrations.
- **PostgreSQL 17** — the only supported datastore; no in-memory fallback.
- **firebase-admin** — verifies caller-supplied Firebase ID tokens (`app/auth.py`).
- **pytest** + **httpx**/FastAPI `TestClient` — unit, integration, and repository tests,
  all running against a real local Postgres instance.
- **Docker** (`Dockerfile`, `docker-compose.yml`) — single-worker containerized run (see
  Deployment below).

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
   the same caveat. `app/services/authorization.py` holds two small,
   stateless, dependency-free helpers (`ensure_owner`,
   `ensure_owner_or_related`) used by every service to raise `ForbiddenError`
   for "caller must be the owner" / "caller must be the owner or related via
   some membership/assignment" checks — extracted because that `if
   current_user_id is not None and current_user_id != owner: raise
   ForbiddenError(...)` shape previously appeared, hand-copied, in 8+ call
   sites across every service.
3. **repositories** — `BaseRepository[T]` (abstract) defines `add`, `get`,
   `update`, `list_all`. Each entity has one Postgres-backed repository
   class (`UserRepository`, `GroupRepository`, `TaskRepository`,
   `UserGroupRepository`, `TaskGroupRepository`) implementing it via a
   SQLAlchemy `Session`, mapping Pydantic domain models to/from the ORM rows
   defined in `app/db/orm_models.py`. One repository per entity/relationship.
   A couple (`UserGroupRepository.delete`, `TaskGroupRepository.update`
   clearing `assigneeId`) add entity-specific methods beyond the abstract
   interface, same rationale as the service-layer exceptions above.
4. **models** — Domain entities (Pydantic models), the shape of truth held by
   repositories.
5. **schemas** — API request/response contracts (Pydantic models), decoupled
   from domain models so the wire format can evolve independently of the
   internal shape. Every schema's fields currently mirror its domain model
   exactly (a deliberate YAGNI-adjacent choice: the seam exists so the two
   *can* diverge later without a breaking change, even though they don't
   diverge yet).

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

Note: authentication (`app/auth.py::verify_firebase_token`) is wired in via
`Depends` on each router the same way, but the Firebase Admin SDK itself is
initialized as a *module-level* side effect in `app/auth.py`, not from this
composition root — see `OpenPoints.md`'s clean-architecture follow-ups for
why that's a structural inconsistency worth revisiting.

## Authentication & Request Identity

Every route depends on `verify_firebase_token` (`app/auth.py`), which reads
the `Authorization: Bearer <token>` header, verifies it against Firebase,
and returns the token's `uid` as `current_user_id` — an explicit function
argument threaded from router → service on every endpoint (not
router-level middleware). Services use `current_user_id` for two purposes:

1. **Identity binding on create**: `POST /users`, `POST /groups`, and
   `POST /tasks` never accept an owner/creator ID in the request body — it's
   always `current_user_id`, so a caller can only ever create resources
   attributed to themselves.
2. **Authorization checks on read/write**: passed through to service methods
   (`get_user(..., current_user_id=...)`, `get_group(...)`, etc.), which
   raise `ForbiddenError` (→ HTTP 403) when the caller fails the resource's
   ownership/membership rule.

`User.userId` IS the Firebase `uid` for every user created through this API
— there is no separate identity-mapping table. See `OpenPoints.md`'s "Auth &
authorization" section for the exact ownership rule per endpoint.

Most service methods accept `current_user_id: Optional[str] = None` and
only enforce the check `if current_user_id is not None`. This lets unit
tests call services directly without going through HTTP/auth at all (see
Testing strategy below) — but it also means any *non-test, non-HTTP* future
caller that forgets to pass `current_user_id` silently skips authorization.
Worth keeping in mind before adding new service-to-service or scripted call
sites.

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

## Recurring pattern: auto-bootstrap via direct repository access

Two services create a *second* entity's row as a side effect of creating
the first, and both do it by reaching directly into that second entity's
repository rather than calling its owning service:

- `GroupService.create_group` inserts a `UserGroupRelationship(relationship="SELF")`
  row via `UserGroupRepository`, so a group's creator is always a member.
- `TaskService.create_task` (when `groupId` is set) inserts a
  `TaskGroupRelationship(assigneeId=creator)` row via `TaskGroupRepository`,
  so a task created inside a group is always assigned to its creator.

Both bypass the "natural" service (`UserGroupService.associate` /
`TaskGroupService.assign`) for the same reason: calling it would create a
circular dependency (`UserGroupService` already depends on `GroupService`;
`TaskGroupService` already depends on `TaskService`). Reaching into the
sibling repository directly — rather than the sibling service — is the
resolution used both times.

This is a deliberate, working pattern at two occurrences. `OpenPoints.md`
flags it as a signal to extract a shared abstraction (e.g. a
dependency-free membership/assignment helper) if a third occurrence shows
up, rather than a problem to fix now.

## Entity relationships

- `User` 1—0..N `UserGroupRelationship` N—1 `Group` (many-to-many join with
  a `relationship` label, e.g. "Father"). A group's creator is automatically
  associated with `relationship="SELF"` at creation time (see the
  bootstrap pattern above). Only the group's creator can associate or
  disassociate members (`UserGroupService.associate`/`disassociate`); the
  creator themselves can never be disassociated (`ERR_TASKS_009`).
- `Task` 0..1—0..1 `Group` via `Task.groupId` (a task's single "home" group,
  set only at creation, immutable thereafter — separate from the
  many-to-many `TaskGroupRelationship` join below). Creating a task with a
  `groupId` requires the creator to already be that group's creator or a
  member (`GroupService.get_group`'s existing check), and automatically
  creates a `TaskGroupRelationship` row with `assigneeId` = the creator (see
  the bootstrap pattern above).
- `Task` 0..1—0..N `TaskGroupRelationship` N—0..1 `Group`, with an optional
  `assigneeId` (a `User`) on each join row. A task's creator CAN be its own
  assignee (the prior `ERR_TASKS_005` constraint was retired). Reassignment
  (`PATCH .../assignee`) requires the new assignee to already be a group
  member; there is no API to clear an assignee back to `None`.
- Both join tables enforce their uniqueness at the DB level
  (`uq_user_groups_user_id_group_id`, `uq_group_tasks_task_id_group_id`),
  which is what the `DUPLICATE_GROUP_MEMBERSHIP`/`ERR_TASKS_003` check
  ultimately backstops (see `OpenPoints.md` for the race-condition caveat on
  that check-then-insert pattern).

## Request flow example (create user)

`POST /api/v1/users` → `api/v1/users.create_user` → `UserService.create_user`
(`userId` = the caller's Firebase `current_user_id`, plus timestamps, builds
`User` domain model) → `UserRepository.add` (inserts a row via SQLAlchemy) →
router maps `User` domain model to `UserResponse` schema → FastAPI
serializes to JSON.

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
- Concurrency/race-condition behavior (see `OpenPoints.md`) is not covered
  by any test tier today.

## API Endpoint Inventory (v1)

| Method | Path | Purpose | Who may call it |
|---|---|---|---|
| POST | /api/v1/users | Create a user (self, from token) | Any authenticated caller |
| GET | /api/v1/users/{userId} | Fetch a user | That user |
| PATCH | /api/v1/users/{userId} | Update name/phone/email | That user |
| PATCH | /api/v1/users/{userId}/status | Toggle ACTIVE/IN-ACTIVE | That user |
| POST | /api/v1/groups | Create a group (creator = self, from token) | Any authenticated caller |
| GET | /api/v1/groups/{groupId} | Fetch a group | Creator or member |
| GET | /api/v1/users/{userId}/groups | Fetch groups created by a user | That user |
| PATCH | /api/v1/groups/{groupId} | Update name/desc/iconUrl (not category) | Creator |
| PATCH | /api/v1/groups/{groupId}/status | Toggle ACTIVE/IN-ACTIVE | Creator |
| GET | /api/v1/groups/{groupId}/members | Fetch a group's members | Creator or member |
| POST | /api/v1/groups/{groupId}/members | Associate a user to a group | Creator only |
| DELETE | /api/v1/groups/{groupId}/members/{userId} | De-associate a user from a group | Creator only; creator itself is never removable |
| POST | /api/v1/tasks | Create a task (optional groupId; auto-assigns creator if set) | Any authenticated caller |
| GET | /api/v1/tasks | List tasks created by or assigned to the caller | Self (implicit) |
| GET | /api/v1/tasks/{taskId} | Fetch a task | Creator or assignee |
| PATCH | /api/v1/tasks/{taskId} | Update title/desc | Creator |
| PATCH | /api/v1/tasks/{taskId}/state | Move task to a new state | Creator or assignee |
| PATCH | /api/v1/tasks/{taskId}/due-date | Update due date | Creator or assignee |
| PATCH | /api/v1/groups/{groupId}/tasks/{taskId}/assignee | Reassign task's assignee within a group | Creator or any group member |
| GET | /api/v1/groups/{groupId}/tasks | Fetch all tasks belonging to a group | Creator or any member |

The manual `POST .../assignee` (assign) endpoint was removed; see
`OpenPoints.md`'s Design notes for what replaced it. Full per-error-code and
edge-case authorization detail lives in `OpenPoints.md`'s "Auth &
authorization" section — this table is the structural summary.

## Deployment

`Dockerfile` builds a single image; both it and `docker-compose.yml` run
`uvicorn` with no `--workers` flag, i.e. a single worker. Now that all state
lives in Postgres (not in-memory), a single worker is a conservative
default rather than a hard requirement — the API layer itself has no
shared in-process state left to make multi-worker unsafe — but running
multiple workers hasn't been tried or load-tested, so treat it as
unverified rather than endorsed. See `OpenPoints.md`'s Deployment section
for the unresolved Firebase credentials-at-build-time gap and the
not-yet-verified `docker compose up` run.
