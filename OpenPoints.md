# TaskNest — Open Points / Future Work

Tracked gaps and decisions deferred during the initial build. Revisit these
before any production use.

## Persistence
- The app is backed entirely by PostgreSQL 17 via SQLAlchemy + psycopg3,
  with Alembic managing schema migrations (`migrations/`). No in-memory
  storage remains anywhere in the codebase, including tests — the full
  suite (`tests/unit`, `tests/integration`, `tests/repositories`) requires
  a running local Postgres (`tasks_net_db_test`).
- `docker-compose.yml` runs Postgres as its own `db` service
  (`postgres:17-alpine`, named volume `pgdata`), with the `api` service
  running `alembic upgrade head` automatically on container start.
  Credentials/DB name/port are parameterized via `${VAR}` substitution, not
  hardcoded — `.env` (UAT, the default) and `.env.prod` (PROD, via
  `docker compose --env-file .env.prod up`) supply the values, each with
  its own `COMPOSE_PROJECT_NAME` so the two environments' containers and
  volumes stay isolated. Neither file holds a real secret. Local
  (non-Docker) development still targets the Postgres 17 instance installed
  via Homebrew (`brew services start postgresql@17`).

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
  - Group membership: only the group's creator can associate or
    disassociate members (`ForbiddenError`/403 otherwise) — not
    creator-or-member as with other group endpoints. The creator can never
    be disassociated (`BadRequestError`/`ERR_TASKS_009`). Every group
    automatically includes its creator as a `relationship="SELF"` member
    from creation.
  - Tasks (read/state/due-date): caller must be the creator or the
    assignee. Task meta update: creator only. Assign: creator only
    (endpoint removed — assignment now only happens via `POST
    /api/v1/tasks` with a `groupId`, which auto-assigns the creator).
    Reassign: creator or any group member (a deliberate divergence from
    assign's creator-only rule). Group-tasks listing: creator or any
    member.
  - `GET /api/v1/tasks`: returns tasks created by or assigned to the
    caller, sorted by most recently updated/created first.
  - `updatedBy` on task updates (meta/state/due-date) is no longer a
    request-body field — it's always `current_user_id`.
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
`app.exceptions.BadRequestError` is raised by `TaskGroupService.assign`
(no longer HTTP-reachable — see Design notes below), `TaskGroupService.reassign`,
`TaskService.update_task_state`, `UserGroupService.associate`, and
`UserGroupService.disassociate` for their respective validation rules;
routers translate it to HTTP 400 with a JSON body of the form
`{"detail": {"errorCode": "ERR_TASKS_00N", "message": "..."}}`.
See `app.exceptions.ErrorCode` and `ERROR_CODE_MESSAGES` for the current
code -> message mapping:

| Code | Meaning |
|---|---|
| `ERR_TASKS_001` | Assignee is not a member of the target group |
| `ERR_TASKS_002` | Task is already in the requested state (any no-op state transition, not just COMPLETED->COMPLETED) |
| `ERR_TASKS_003` | User is already associated with this group |
| `ERR_TASKS_007` | Requested Task assignee is same as current assignee |
| `ERR_TASKS_008` | Requested Assignee is not part of the Group |
| `ERR_TASKS_009` | Group creator cannot be de-associated with group |

Note: `ERR_TASKS_004`, `ERR_TASKS_005`, and `ERR_TASKS_006` are intentionally
unused/retired. `ERR_TASKS_004` was folded into the broadened `ERR_TASKS_002`.
`ERR_TASKS_005` (`TASK_CREATOR_CANNOT_BE_ASSIGNEE`) and `ERR_TASKS_006`
(`GROUP_CREATOR_CANNOT_BE_MEMBER`) were both retired business rules: task
creators can be their own task's assignee (both `assign` and `reassign` skip
the group-membership check for the task's own creator), and group creators
are now always members (`relationship="SELF"`) of their own group.

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
- `TaskGroupService.unassign` no longer exists (removed along with its
  `DELETE .../assignee/{assigneeId}` route) — reassignment is now done via
  `PATCH .../assignee` (`reassign`), which requires an existing assignment
  and a different target assignee. There is currently no way to clear an
  assignee back to `None` via the API.
- `POST /api/v1/groups/{groupId}/tasks/{taskId}/assignee` (manual assign) no
  longer exists either. `TaskGroupService.assign()` (the service method) is
  kept because unit tests still use it directly as fixture setup, but
  nothing in production calls it — the only ways a task gets an initial
  assignment now are auto-assign-on-create-with-`groupId`, or (once one
  exists) `PATCH .../assignee` (`reassign`).
- A `TaskGroupRelationship` row created automatically at task-creation time
  (when `groupId` is set) is indistinguishable from one created via the
  manual `assign`/`reassign` endpoints — there's no "origin" flag.
- `Task.groupId` (a task's single "home" group, set only at creation) and
  the many-to-many `TaskGroupRelationship`/`group_tasks` join table are
  independent concepts that happen to usually agree: nothing prevents a
  future `assign`/`reassign` call from pointing a task's assignment at a
  *different* group than its `groupId`. This was already true before
  `groupId` existed (the join table has always been independent of
  anything on `Task`) — not a new gap, just newly visible.

## Code quality / clean-architecture follow-ups (2026-07-05 review)

Found while reviewing the full codebase for clean-architecture adherence. None of these
are bugs affecting current documented behavior — they're structural debt worth planning
around before the API surface grows further.

- **Repository `update()` methods assume the row already exists.** `UserRepository.update`,
  `GroupRepository.update`, `TaskRepository.update`, `UserGroupRepository.update`, and
  `TaskGroupRepository.update` all do `row = self._session.get(Row, id)` and immediately
  mutate `row.<field>` with no `None` check. Every current call site is preceded by a
  service-level `get_*()` that already raised `NotFoundError` if missing, so this can't
  fire under today's single-request flow — but it means the repository layer silently
  depends on an un-enforced caller invariant instead of translating a missing row into a
  domain exception itself. A future caller that skips the pre-fetch (or a race between
  fetch and update once delete endpoints exist) gets a raw `AttributeError` instead of a
  handled 404/409.
- **Check-then-write races aren't translated to domain exceptions.** `UserService.create_user`
  (checks `get(user_id) is None` then inserts), `UserGroupService.associate` (checks
  `is_member` then inserts), and `TaskGroupService.assign`'s insert branch all do a
  read-then-write with no transaction-level guard. The DB-level unique constraints
  (`uq_user_groups_user_id_group_id`, `uq_group_tasks_task_id_group_id`, the `users` PK)
  will correctly reject a concurrent duplicate, but that surfaces as a raw SQLAlchemy
  `IntegrityError` → unhandled 500, not the `ConflictError`/`ERR_TASKS_003` the
  single-request path already returns for the same logical conflict. Not covered by tests
  (see the concurrency note under Testing below). Fix would be catching `IntegrityError`
  at the repository or service layer and re-raising as the appropriate domain exception.
- **`GroupService.get_group` and `UserGroupService.is_member` independently implement the
  same "is this user a member of this group" query**
  (`UserGroupRepository.find_by_user_and_group(...) is not None`), because `GroupService`
  cannot depend on `UserGroupService` (the latter already depends on the former — see
  `Arch.md`'s "recurring pattern" section) and so reaches into `UserGroupRepository`
  directly instead of delegating. The same shape applies to `GroupService.create_group`'s
  direct `UserGroupRepository.add(...)` call and `TaskService.create_task`'s direct
  `TaskGroupRepository.add(...)` call. Two instances of this shape is a pattern, not (yet)
  a problem; a third would be a signal to extract a shared, dependency-free
  membership/assignment helper both sides can use instead of hand-duplicating the query.
- **`TaskGroupService.assign()`'s inline comment is now stale.** It still says "A group's
  creator can never be a UserGroupRelationship member row (GROUP_CREATOR_CANNOT_BE_MEMBER)"
  — that rule and error code (`ERR_TASKS_006`) were retired; group creators are now always
  `SELF` members. `assign()` itself is no longer HTTP-reachable (its route was removed —
  see Design notes above) and is kept only for test fixture setup, so this is low-urgency,
  but the comment should be corrected, and/or the now-unnecessary
  `assignee_id != task.createdBy` exemption should be dropped to match `reassign()`'s
  simplified `is_member`-only check.
- **Response-schema conversion isn't centralized.** `app/api/v1/users.py`, `groups.py`, and
  `tasks.py` each define a local `_to_response()` helper; `user_group.py` and
  `task_group.py` instead inline `XResponse(**relationship.model_dump())` /
  `TaskResponse(**t.model_dump())` at each call site. Today every domain model's fields
  match its schema's fields exactly, so both approaches produce identical output — but if
  a schema ever needs a computed/renamed/hidden field, only the routers using the named
  helper would pick up the change; the inline call sites would silently keep serializing
  raw `model_dump()` output instead.
- **`app/auth.py` initializes the Firebase Admin SDK and reads
  `firebase-adminsdk.json` at module import time**, not through `app/dependencies.py` (the
  documented sole composition root for repositories/services). Any import of `app.main`
  (including via `tests/conftest.py`) triggers this side effect before
  `app.dependency_overrides` ever gets a chance to bypass `verify_firebase_token` — meaning
  the credentials file must exist on disk to run the test suite at all, even though no
  test actually calls real Firebase. Consider lazy-initializing the Firebase app inside
  `verify_firebase_token` on first call instead of at import time.
- **`TaskService.get_tasks_for_user` fetches each assigned task individually inside a
  loop** (`self._repository.get(rel.taskId)` per row returned by `list_by_assignee`)
  instead of a single batch query — an N+1 query pattern that will get worse as
  `list_by_assignee` results grow. Not urgent at current scale, but worth a
  `list_by_ids`-style batch method on `TaskRepository`/`BaseRepository` if this list ever
  needs pagination (see API surface gaps above).
- **`tests/conftest.py`'s `client` and `unauthenticated_client` fixtures duplicate the
  entire repository/service wiring block verbatim** — the only difference between them is
  whether `verify_firebase_token` is overridden. Worth extracting into a shared
  `_build_services(db_session)` helper.

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
  fails with "command not found" as of this writing — reconfirmed when the
  `db` service was added). The `Dockerfile` and `docker-compose.yml`
  (including the new `db` service, auto-migration-on-startup, and
  `depends_on: service_healthy` gating) were therefore verified only
  indirectly — by running the exact `alembic upgrade head`/`uvicorn`
  commands the image uses directly against a throwaway database on the
  local Postgres 17 instance, and by parsing `docker-compose.yml` as YAML
  to confirm its structure, never through an actual `docker build` or
  `docker compose up`. Install Docker Desktop (or the Docker Engine CLI) on
  this machine and run `docker compose up --build` at least once to confirm
  the full stack (API + Postgres, auto-migrated) actually builds, starts in
  the right order, and serves traffic before relying on it for any real
  deployment or CI step.
- The Firebase service-account credential (`app/firebase/firebase-adminsdk.json`)
  is required at container start but is gitignored, so a plain
  `docker build` from a clean checkout will NOT have it. Needs an explicit
  decision: bake a build-time secret (Docker BuildKit `--secret`), mount it
  as a runtime volume, or inject the JSON contents via an env var and have
  `app/auth.py` support loading credentials from an env-var string in
  addition to a file path. Not resolved by this change.
- UAT and PROD environments (`.env` / `.env.prod`) currently only vary
  Postgres credentials/DB name/port — both still share the single
  build-time-baked Firebase credentials file (see the bullet above). If
  UAT and PROD ever need separate Firebase projects, that requires solving
  the credentials-injection gap first (mounting the credentials file at
  runtime instead of `COPY`-ing it at build time), which isn't done here.
