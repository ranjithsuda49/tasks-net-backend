# TaskNest

Backend REST API for TaskNest — Users, Groups, Tasks, and their
relationships — built with FastAPI and in-memory storage.

## Setup

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

## Run

uvicorn app.main:app --reload

API docs (Swagger UI) at http://localhost:8000/docs

## Test

pytest -v

See `Arch.md` for architecture and the full endpoint inventory, and
`OpenPoints.md` for known gaps and deferred decisions.
