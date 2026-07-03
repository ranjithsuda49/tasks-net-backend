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
