# TaskNest — Open Points / Future Work

Tracked gaps and decisions deferred during the initial build. Revisit these
before any production use.

## Persistence
- The app is backed entirely by PostgreSQL 17 via SQLAlchemy + psycopg3,
  with Alembic managing schema migrations (`migrations/`). No in-memory
  storage remains anywhere in the codebase, including tests — the full
  suite (`tests/unit`, `tests/integration`, `tests/repositories`) requires
  a running local Postgres (`tasks_net_db_test`).
- `docker-compose.yml` does not run Postgres — local development targets
  the Postgres 17 instance installed via Homebrew (`brew services start
  postgresql@17`). Revisit if/when this needs to run in Docker.

## Auth & authorization
- Authentication AND ownership authorization now exist on every endpoint,
  including all three creation endpoints.
  `current_user_id: str = Depends(verify_firebase_token)` is an explicit
  function argument on every route (moved off the old router-level
  `dependencies=[...]` wiring), threaded into the service layer, which
  raises `app.exceptions.ForbiddenError` (→ HTTP 403) when the rule fails:
  - `POST /api/v1/users`: no request-body `userId` field — `userId` is
    always `current_user_id` (the caller's Firebase uid). Calling it
    again for a uid that already has a `User` row raises `ConflictError`
    (→ HTTP 409), since re-registration isn't an update path.
  - `POST /api/v1/groups`: no request-body `groupCreaterId` field —
    `groupCreaterId` is always `current_user_id`.
  - `POST /api/v1/tasks`: no request-body `createdBy` field — `createdBy`
    is always `current_user_id`.
  - Users (read/update/status): caller must be the `userId` in the path.
  - Groups (read): caller must be the creator or a member. Groups
    (write): creator only. `GET /api/v1/users/{userId}/groups`: caller
    must be that `userId`.
  - Group membership (read/associate): caller must be the creator or a
    member. Disassociate: caller must be the member being removed, OR
    the group's creator.
  - Tasks (read/state/due-date): caller must be the creator or the
    assignee. Task meta update: creator only. Assign/unassign: creator
    only.
  - `GET /api/v1/tasks`: returns tasks created by or assigned to the
    caller, sorted by most recently updated/created first.
- The Firebase `uid`-vs-`User.userId` ID-space mismatch noted in an
  earlier revision of this doc is resolved for any user created from now
  on: `UserService.create_user` requires an explicit `user_id` and the
  router passes `current_user_id` (the Firebase uid) as that value, so
  `User.userId` IS the Firebase uid going forward — no separate mapping
  column needed.
- Local prerequisite: `app/firebase/firebase-adminsdk.json` (a Firebase
  service-account credential, gitignored via `app/firebase/` in
  `.gitignore` and never committed) must be present on disk before the
  app can start — `app/auth.py` reads it at import time. The path is
  overridable via the `FIREBASE_CREDENTIALS_PATH` env var.

## Error codes
`app.exceptions.BadRequestError` is raised by `TaskGroupService.assign`,
`TaskService.update_task_state`, and `UserGroupService.associate` for their
respective validation rules; routers translate it to HTTP 400 with a JSON
body of the form `{"detail": {"errorCode": "ERR_TASKS_00N", "message": "..."}}`.
See `app.exceptions.ErrorCode` and `ERROR_CODE_MESSAGES` for the current
code -> message mapping:

| Code | Meaning |
|---|---|
| `ERR_TASKS_001` | Assignee is not a member of the target group |
| `ERR_TASKS_002` | Task is already in the requested state (any no-op state transition, not just COMPLETED->COMPLETED) |
| `ERR_TASKS_003` | User is already associated with this group |
| `ERR_TASKS_005` | Task creator cannot be assigned to their own task |
| `ERR_TASKS_006` | Group creator cannot be a member of their own group |

Note: `ERR_TASKS_004` is intentionally unused. The original ask called for
a separate "task already in requested state" code, but that was folded
into a broadened `ERR_TASKS_002` instead of introduced as a new,
overlapping code.

## API surface gaps
- No delete endpoints for `User` or `Group` (spec only asks for status
  toggling, not hard delete) — confirm this is intentional product
  behavior, not an oversight.
- No pagination, filtering, or sorting on list endpoints (e.g.
  "fetch all groups created by user") — fine at small scale, will need
  pagination once data volume grows.
- No bulk operations (e.g. bulk task creation/assignment).
- No GET endpoint to read a user's memberships (i.e. "all groups a given
  user belongs to") — only the group → members direction exists
  (`GET /api/v1/groups/{groupId}/members`).

## Design notes / asymmetries
- `UserGroupService.disassociate` (`app/services/user_group_service.py`)
  hard-deletes the `UserGroupRelationship` row, while
  `TaskGroupService.unassign` (`app/services/task_group_service.py`)
  instead sets `assigneeId=None` on the `TaskGroupRelationship` row and
  keeps it. This is intentional: the Task-Group relationship row
  represents "this task is associated with this group," with `assigneeId`
  as a mutable sub-field of that association, so removing the assignee
  doesn't remove the association. Don't assume symmetry between these two
  removal semantics when reading or extending this code.

## Observability & ops
- No structured logging, request tracing, or metrics.
- No rate limiting.
- No OpenAPI examples/descriptions beyond FastAPI's auto-generated schema
  from Pydantic models — worth enriching for consumers once the API
  stabilizes.

## Testing
- Unit and integration tests cover the happy paths and documented error
  paths (404s/400s) for each entity. Concurrency/race-condition testing
  against Postgres under concurrent writes is not covered.

## Deployment
- Docker is not installed on this development machine (`docker --version`
  fails with "command not found" as of this writing). The `Dockerfile` and
  `docker-compose.yml` were therefore verified only indirectly — by running
  the exact `pip install`/`uvicorn` commands the image uses directly against
  the local `.venv` — never through an actual `docker build` or
  `docker compose up`. Install Docker Desktop (or the Docker Engine CLI) on
  this machine and run `docker compose up --build` at least once to confirm
  the image actually builds and serves traffic before relying on it for any
  real deployment or CI step.
- The Firebase service-account credential (`app/firebase/firebase-adminsdk.json`)
  is required at container start but is gitignored, so a plain
  `docker build` from a clean checkout will NOT have it. Needs an explicit
  decision: bake a build-time secret (Docker BuildKit `--secret`), mount it
  as a runtime volume, or inject the JSON contents via an env var and have
  `app/auth.py` support loading credentials from an env-var string in
  addition to a file path. Not resolved by this change.
