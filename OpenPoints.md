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
- `PATCH /api/v1/tasks/{task_id}/due-date` requires a `taskDueDate` value
  (`TaskDueDateUpdateRequest.taskDueDate: datetime`, not `Optional`), so
  there is currently no way to clear a task's due date back to `null` via
  the API — even though `Task.taskDueDate` on the domain model itself is
  `Optional[datetime]`.

## API surface gaps
- No delete endpoints for `User` or `Group` (spec only asks for status
  toggling, not hard delete) — confirm this is intentional product
  behavior, not an oversight.
- No pagination, filtering, or sorting on list endpoints (e.g.
  "fetch all groups created by user") — fine at small scale, will need
  pagination once data volume grows.
- No bulk operations (e.g. bulk task creation/assignment).
- No GET endpoint to read a group's members or a user's memberships — only
  `POST`/`DELETE` exist for `User`-`Group` associations. As a result,
  `InMemoryUserGroupRepository.list_by_group` is currently dead code in
  production (only exercised by tests, via `UserGroupService.list_by_group`).
  This matches the original spec, which only asked for associate/
  de-associate, so it's not a bug — just a gap for a future task.

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
  paths (404s) for each entity. Concurrency/race-condition testing on the
  in-memory stores is not covered.
