# TaskNest

Backend REST API for TaskNest — Users, Groups, Tasks, and their
relationships — built with FastAPI and PostgreSQL.

## Features

- **Users** — create, fetch, update (name/phone/email), toggle ACTIVE/IN-ACTIVE status.
- **Groups** — create, fetch, update (name/desc/iconUrl), toggle status; fetch all groups created by a user.
- **User-Group relationships** — associate/de-associate a user with a group (e.g. "Father" of a "Family" group).
- **Tasks** — create (optionally for a group, auto-assigning the creator), fetch, update title/desc, move between states (TODO / IN-PROGRESS / COMPLETED), update due date.
- **Task-Group relationships** — assign or reassign a task to a user within a group; list all tasks belonging to a group.

See `Arch.md` for the full endpoint inventory.

## Authentication & ownership

Every endpoint requires a Firebase ID token (`Authorization: Bearer <token>`).
The authenticated caller's uid drives both identity and ownership — it is
never taken from the request body:

- `POST /api/v1/users` — no `userId` field; the new user's `userId` is the
  caller's Firebase uid. Calling it again for a uid that already has a user
  returns `409 Conflict`.
- `POST /api/v1/groups` — no `groupCreaterId` field; the group's creator is
  the caller.
- `POST /api/v1/tasks` — no `createdBy` field; the task's creator is the
  caller.
- All other endpoints enforce ownership (e.g. only a group's creator or
  members can fetch it) and return `403 Forbidden` otherwise.

See `OpenPoints.md` for the full rule-by-rule breakdown.

## Requirements

Python 3.13+

## Setup

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

## Run

uvicorn app.main:app --reload

API docs (Swagger UI) at http://localhost:8000/docs, health check at
http://localhost:8000/health

## Docker

docker compose up --build

API available at http://localhost:8000 (Swagger UI at /docs). Postgres now
runs as its own `db` service (named volume `pgdata` persists data across
restarts), and the `api` service runs `alembic upgrade head` automatically
before starting — no manual database setup needed. The image installs only
`requirements.txt` (no test tooling) and runs a single Uvicorn worker.

## Test

pytest -v

See `Arch.md` for architecture and the full endpoint inventory, and
`OpenPoints.md` for known gaps and deferred decisions.

## PostgreSQL

The app is backed entirely by PostgreSQL 17 via SQLAlchemy + psycopg3, with
Alembic managing schema migrations. PostgreSQL 17 is installed locally via
Homebrew.

Install:

    brew install postgresql@17

Start (background service, restarts at login):

    brew services start postgresql@17

Stop:

    brew services stop postgresql@17

Check status:

    brew services list | grep postgresql
    pg_isready

### Database setup (one-time)

    createdb tasks_net_db
    createdb tasks_net_db_test
    alembic upgrade head

### Running the test suite

The full suite (`pytest -v`) requires the local Postgres service to be
running (`brew services start postgresql@17`) and both databases created.
