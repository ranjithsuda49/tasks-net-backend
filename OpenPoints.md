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
- No authentication or authorization exists on any endpoint. Anyone can
  create/update any user, group, or task, or assign tasks to arbitrary
  users. Needs a decision on auth scheme (session, JWT, API key) before
  this is exposed beyond local development.

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
