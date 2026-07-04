# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

TaskNest: a FastAPI backend for Users, Groups, Tasks, and their relationships
(User↔Group membership, Task↔Group assignment), backed entirely by in-memory
repositories (no database). See `requirements.md` for the original spec,
`Arch.md` for the full architecture writeup and endpoint inventory, and
`OpenPoints.md` for known gaps/deferred decisions — check `OpenPoints.md`
before treating something there as an oversight to fix.

## Development workflow

For any build/feature/bugfix work, prefer the `superpowers` skills as the
primary workflow: `brainstorming` to scope the change, `writing-plans` for a
TDD-structured plan, `executing-plans`/`subagent-driven-development` to
implement it task-by-task, `systematic-debugging` for bugs, and
`finishing-a-development-branch` to wrap up (verify tests, then
merge/push/keep/discard). Only fall back to ad-hoc planning/implementation
if the `superpowers` skills aren't available in the current environment.

## Commands

Requires Python 3.13 (matches `Dockerfile` and the committed `.venv`).

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt   # installs requirements.txt + pytest/httpx

uvicorn app.main:app --reload         # run the API at http://localhost:8000
                                       # Swagger UI at /docs, health check at /health

pytest -v                             # full suite
pytest tests/unit -v                  # unit tests only
pytest tests/integration -v           # integration tests only
pytest tests/unit/test_task_service.py::test_name -v   # single test

docker compose up --build             # containerized run (single worker — see below)
```

There is no lint/format/type-check tooling configured in this repo.

## Architecture

Layers, each with one reason to change:

1. **`app/api/v1/`** — FastAPI routers. HTTP only: parse the request, call one
   service method, translate the service's domain exceptions to
   `HTTPException`, return a response schema. No business logic here.
2. **`app/services/`** — business logic. Most services take a
   `BaseRepository` abstraction via constructor injection. `GroupService`,
   `UserGroupService`, and `TaskGroupService` instead depend on a concrete
   `InMemory*Repository` because they need an entity-specific query method
   (`list_by_creator`, `find_by_user_and_group`, etc.) not on the generic
   `BaseRepository[T]` interface. Services also compose other services
   (e.g. `TaskGroupService` depends on `TaskService`, `GroupService`,
   `UserService`, `UserGroupService`) rather than reaching into other
   repositories directly.
3. **`app/repositories/`** — `BaseRepository[T]` (abstract: `add`, `get`,
   `update`, `list_all`) with one `InMemory*Repository` per entity, each a
   `dict[str, T]` keyed by ID.
4. **`app/models/`** — domain entities (Pydantic), the shape repositories
   store.
5. **`app/schemas/`** — API request/response contracts (Pydantic), kept
   separate from domain models so the wire format can evolve independently.

**Composition root**: `app/dependencies.py` is the only place that
constructs repositories and services. Repository providers are
`@lru_cache`d (one singleton per process, since in-memory data must persist
across requests); services are built fresh per request via FastAPI's
`Depends`, composed from the cached repositories/services.

**Exception → HTTP translation**: services raise `app.exceptions.NotFoundError`,
`ConflictError`, or `BadRequestError` (the latter carries an `error_code` from
`ErrorCode`/`ERROR_CODE_MESSAGES` and renders as
`{"detail": {"errorCode": "ERR_TASKS_00N", "message": "..."}}`). Routers
catch these and raise the equivalent `HTTPException` — never let a domain
exception escape a router uncaught.

**Tests** (`tests/conftest.py`): the `client` fixture builds a fresh set of
repositories/services per test and overrides the service-level providers via
`app.dependency_overrides`, so tests never leak state into each other but a
single test's user/group/task creations remain consistent with each other.
Unit tests (`tests/unit/`) instantiate a service directly with a fresh
in-memory repo, bypassing HTTP; integration tests (`tests/integration/`) go
through the real FastAPI app via `TestClient`.

## Things that aren't obvious from one file

- `UserGroupService.disassociate` hard-deletes the join row, but
  `TaskGroupService.unassign` only clears `assigneeId` and keeps the row —
  intentional asymmetry (task↔group association vs. its mutable assignee
  sub-field), not a bug. Don't "fix" one to match the other.
- Multi-worker deployment is unsafe: each Uvicorn worker gets its own
  independent in-memory state, since there's no shared store. The
  `Dockerfile`/`docker-compose.yml` intentionally run a single worker.
