# TaskNest

Backend REST API for TaskNest — Users, Groups, Tasks, and their
relationships — built with FastAPI and in-memory storage.

## Setup

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

## Run

uvicorn app.main:app --reload

API docs (Swagger UI) at http://localhost:8000/docs

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
