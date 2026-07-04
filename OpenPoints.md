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
- Authentication (not authorization) now exists on every endpoint except
  `POST /api/v1/users` (user creation, which must remain callable
  pre-signup). Callers must send `Authorization: Bearer <Firebase_ID_Token>`;
  `app.auth.verify_firebase_token` (a FastAPI dependency wired in at the
  router level for `groups.py`, `user_group.py`, `tasks.py`,
  `task_group.py`, and per-route for the 3 non-create routes in
  `users.py`) validates the token via `firebase_admin.auth.verify_id_token`
  and rejects missing/malformed/invalid/expired tokens with HTTP 401.
- This is authentication only — it proves a valid Firebase-issued token
  was presented, nothing more. There is still NO authorization/ownership
  enforcement anywhere: any authenticated Firebase user can read or
  mutate any User, Group, or Task regardless of who created it. The
  Firebase `uid` extracted from the token is returned by
  `verify_firebase_token` but not currently checked against resource
  ownership (e.g. `Group.groupCreaterId`, `Task.createdBy`) in any service.
- The Firebase `uid` has NO mapping to this app's own `User.userId`.
  These are two different, unrelated ID spaces: `User.userId` is a
  server-generated UUID4 created by `UserService.create_user` with no
  link back to Firebase identity. A future iteration would need an
  explicit `User.firebaseUid` column (or equivalent lookup) plus
  per-route ownership checks before this becomes real authorization.
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
