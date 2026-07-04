# TaskNest

Backend REST API for TaskNest — Users, Groups, Tasks, and their
relationships — built with FastAPI and in-memory storage.

## Features

- **Users** — create, fetch, update (name/phone/email), toggle ACTIVE/IN-ACTIVE status.
- **Groups** — create, fetch, update (name/desc/iconUrl), toggle status; fetch all groups created by a user.
- **User-Group relationships** — associate/de-associate a user with a group (e.g. "Father" of a "Family" group).
- **Tasks** — create, fetch, update title/desc, move between states (TODO / IN-PROGRESS / COMPLETED), update due date.
- **Task-Group relationships** — assign/unassign a task to a user within a group.

See `requirements.md` for the original spec and `Arch.md` for the full endpoint inventory.

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
Uvicorn worker — the in-memory store isn't safe to share across workers,
see `OpenPoints.md`.

## Test

pytest -v

See `Arch.md` for architecture and the full endpoint inventory, and
`OpenPoints.md` for known gaps and deferred decisions.

## PostgreSQL (local, for future DB work)

The app currently uses in-memory storage only — no code connects to
Postgres yet (see `OpenPoints.md`). PostgreSQL 17 is installed locally via
Homebrew in preparation for that work.

Install:

    brew install postgresql@17

Start (background service, restarts at login):

    brew services start postgresql@17

Stop:

    brew services stop postgresql@17

Check status:

    brew services list | grep postgresql
    pg_isready
