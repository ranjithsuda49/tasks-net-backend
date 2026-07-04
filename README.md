# TaskNest

Backend REST API for TaskNest — Users, Groups, Tasks, and their
relationships — built with FastAPI and PostgreSQL.

## Features

- **Users** — create, fetch, update (name/phone/email), toggle ACTIVE/IN-ACTIVE status.
- **Groups** — create, fetch, update (name/desc/iconUrl), toggle status; fetch all groups created by a user.
- **User-Group relationships** — associate/de-associate a user with a group (e.g. "Father" of a "Family" group).
- **Tasks** — create, fetch, update title/desc, move between states (TODO / IN-PROGRESS / COMPLETED), update due date.
- **Task-Group relationships** — assign/unassign a task to a user within a group.

See `Arch.md` for the full endpoint inventory.

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

API available at http://localhost:8000 (Swagger UI at /docs). The image
installs only `requirements.txt` (no test tooling) and runs a single
Uvicorn worker. Note: `docker-compose.yml` does not run Postgres — the
containerized `api` service needs a reachable `DATABASE_URL` (e.g.
pointing at the host's local Postgres) to actually connect, see
`OpenPoints.md`.

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
