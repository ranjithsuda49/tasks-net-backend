# TaskNest Docker Compose Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Containerize the existing TaskNest FastAPI app with a `Dockerfile` and `docker-compose.yml` per `requirements.md`, splitting `requirements.txt` into a lean runtime-only file (used by the Docker image) plus a new `requirements-dev.txt` for local test tooling, and then — as a separate follow-up per the user's explicit request — clean up `OpenPoints.md` by removing the gap bullets that prior work has already resolved.

**Architecture:** No application code changes. `Dockerfile` builds a single-stage image from `python:3.13-slim`, installs only `requirements.txt` (fastapi/uvicorn/pydantic — no test tooling), copies `app/`, and runs `uvicorn app.main:app --host 0.0.0.0 --port 8000` with no `--reload` and no `--workers` (the in-memory repositories are not process-safe — see `OpenPoints.md` — so exactly one worker is required). `docker-compose.yml` defines one `api` service building that image and publishing port 8000, matching the existing `/health` endpoint and the port already documented in `README.md`.

**Tech Stack:** Docker, Docker Compose (Compose Spec, no `version:` key), Python 3.13-slim base image. No new Python dependencies — `requirements.txt` is trimmed, not expanded.

## Global Constraints

- `requirements.txt` becomes runtime-only (`fastapi`, `uvicorn[standard]`, `pydantic`) — confirmed explicitly. A new `requirements-dev.txt` adds `pytest`/`httpx` on top via `-r requirements.txt`, for local development and CI.
- The Docker image installs only `requirements.txt` — test tooling never ships in the built image.
- `docker-compose.yml` defines the API service only — no test-runner service/profile, confirmed explicitly. Tests keep running locally via the existing `.venv` + `requirements-dev.txt` workflow.
- The container must run a single Uvicorn worker (no `--workers` flag, no multiple `replicas`) — `OpenPoints.md`'s existing "Persistence" section already documents that the in-memory repositories are not thread-/process-safe across workers; the Docker setup must not violate this.
- Docker is not installed in this development environment (verified: `docker --version` → command not found). Each task's verification must have a fallback that doesn't require an actual `docker build`/`docker compose up` run — validate file syntax and, where possible, prove the underlying commands work by running the equivalent `pip install` / `uvicorn` invocation directly against the local `.venv`.
- `OpenPoints.md` cleanup (Task 4) removes exactly the three "gap" bullets that are marked resolved (assignee-membership check, task-state re-completion guard, duplicate-membership check) — including the third one, which was only "partially fixed" but whose remaining unrestricted-transition behavior is a deliberate design choice, not an open defect, so it is removed too (confirmed explicitly). The "Error codes" reference table/subsection is *not* a gap — it documents currently-active behavior — so it stays, with its intro sentence reworded since it can no longer say "the three fixes above" (those bullets will be gone).

---

## Context

`requirements.md` now asks for a `docker-compose` setup that builds the current Python app, referencing the app's current dependencies and exposed APIs, and explicitly calls out `requirements.txt` as something to review and suggest changes to. The app (`app/main.py`) is a FastAPI service with no external dependencies (in-memory storage only, per `OpenPoints.md`'s "Persistence" section) exposing `/health` plus the `/api/v1/...` routes documented in `Arch.md`; it's normally run locally via `uvicorn app.main:app --reload` on port 8000 (see `README.md`). `requirements.txt` currently bundles both runtime deps (fastapi, uvicorn, pydantic) and test-only deps (pytest, httpx) in one file — clarified during planning that this should be split so the Docker image only installs what it needs to run, with a new `requirements-dev.txt` carrying the test tooling for local/CI use. Separately, the user asked that once this Docker work lands, `OpenPoints.md` be reviewed and the gap bullets that earlier sessions already resolved (visible today as strikethrough "Fixed"/"Partially fixed" text) be removed rather than left marked-but-present.

---

## File Structure

```
requirements.txt              # TRIMMED — runtime-only: fastapi, uvicorn[standard], pydantic
requirements-dev.txt          # NEW — -r requirements.txt, plus pytest, httpx
Dockerfile                    # NEW — python:3.13-slim, installs requirements.txt, runs uvicorn
.dockerignore                 # NEW — excludes .venv, .git, tests/, docs/, caches, etc. from build context
docker-compose.yml            # NEW — single `api` service, builds ., publishes 8000:8000
README.md                     # Setup section points at requirements-dev.txt; new "## Docker" section
OpenPoints.md                 # Task 4 only — remove 3 resolved gap bullets, keep/reword Error codes table
```

---

## Task 1: Split `requirements.txt` into runtime + dev

**Files:**
- Modify: `requirements.txt`
- Create: `requirements-dev.txt`
- Modify: `README.md` (only the "## Setup" section in this task — the "## Docker" section is added in Task 3)

**Interfaces:** None — this task only changes which packages are listed in which file; no code changes, no new Python symbols.

- [ ] **Step 1: Trim `requirements.txt` to runtime-only dependencies**

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
pydantic==2.10.4
```

- [ ] **Step 2: Create `requirements-dev.txt`**

```
-r requirements.txt
pytest==8.3.4
httpx==0.28.1
```

- [ ] **Step 3: Update `README.md`'s "## Setup" section to install from the dev file**

Replace:
```markdown
## Setup

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

With:
```markdown
## Setup

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

(Leave the "## Run" and "## Test" sections untouched in this task.)

- [ ] **Step 4: Verify the split installs cleanly and the app still runs**

Run (reusing the existing `.venv` — this proves `requirements-dev.txt` is a strict superset of what's needed for both running and testing, without requiring a Docker build):
```bash
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -v
```
Expected: `pip install` completes with no errors, and all 62 tests still pass (nothing changed about which packages are ultimately installed for local dev — only `requirements.txt`'s own scope shrank).

- [ ] **Step 5: Commit**

```bash
git add requirements.txt requirements-dev.txt README.md
git commit -m "chore: split requirements.txt into runtime and dev dependency files"
```

---

## Task 2: Add `Dockerfile` and `.dockerignore`

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`

**Interfaces:** None — consumes the trimmed `requirements.txt` from Task 1 and the existing `app/` package and `app/main.py:app`/`/health` endpoint (both unchanged).

- [ ] **Step 1: Write `Dockerfile`**

```dockerfile
FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Note: no `--reload` (that's a local-dev convenience that watches the filesystem — not appropriate for a built image) and no `--workers` (the in-memory repositories are not process-safe across multiple workers — see `OpenPoints.md`'s "Persistence" section — so the default single worker must be preserved).

- [ ] **Step 2: Write `.dockerignore`**

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
.git/
.gitignore
tests/
docs/
.superpowers/
*.md
Dockerfile
docker-compose.yml
.dockerignore
```

- [ ] **Step 3: Verify without a Docker daemon (since Docker is not installed in this environment)**

Since `docker build` cannot run here, verify the Dockerfile's logic is correct by running its two meaningful commands directly against a fresh throwaway venv, proving the exact commands the image would execute actually work:
```bash
python3 -m venv /tmp/docker-verify-venv
source /tmp/docker-verify-venv/bin/activate
pip install --no-cache-dir -r requirements.txt
python -c "import fastapi, uvicorn, pydantic; print('runtime deps import OK')"
deactivate
rm -rf /tmp/docker-verify-venv
```
Expected: `pip install` succeeds using *only* the trimmed `requirements.txt` (no pytest/httpx needed for this), and the import check prints `runtime deps import OK` — this proves the Dockerfile's `RUN pip install -r requirements.txt` step is sufficient for the app to actually start.

If Docker happens to be available in the environment executing this plan, additionally run:
```bash
docker build -t tasknest:verify .
```
Expected: image builds successfully. If Docker is unavailable, skip this and rely on the venv check above — note this in your task report either way.

- [ ] **Step 4: Commit**

```bash
git add Dockerfile .dockerignore
git commit -m "feat: add Dockerfile for TaskNest API"
```

---

## Task 3: Add `docker-compose.yml` and document Docker usage

**Files:**
- Create: `docker-compose.yml`
- Modify: `README.md` (add "## Docker" section)

**Interfaces:** Consumes the `Dockerfile` from Task 2 (via `build: .`) and the existing `/health` endpoint (`app/main.py`) for the healthcheck.

- [ ] **Step 1: Write `docker-compose.yml`**

```yaml
services:
  api:
    build: .
    ports:
      - "8000:8000"
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 3s
      start_period: 5s
      retries: 3
```

- [ ] **Step 2: Add a "## Docker" section to `README.md`**

Insert after the existing "## Run" section (before "## Test"):

```markdown
## Docker

docker compose up --build

API available at http://localhost:8000 (Swagger UI at /docs). The image
installs only `requirements.txt` (no test tooling) and runs a single
Uvicorn worker — the in-memory store isn't safe to share across workers,
see `OpenPoints.md`.
```

- [ ] **Step 3: Verify end-to-end**

If Docker is available in the environment executing this plan:
```bash
docker compose up --build -d
sleep 3
curl -s localhost:8000/health
curl -s -X POST localhost:8000/api/v1/users -H 'Content-Type: application/json' -d '{"firstName":"Ada","lastName":"Lovelace"}'
docker compose down
```
Expected: `/health` returns `{"status":"ok"}`, the POST returns `201` with a generated `userId`.

If Docker is unavailable (as in this development environment — confirmed via `docker --version` failing), instead prove the exact `CMD` the image would run actually serves traffic correctly, using the existing `.venv`:
```bash
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8001 &
sleep 1
curl -s localhost:8001/health
curl -s -X POST localhost:8001/api/v1/users -H 'Content-Type: application/json' -d '{"firstName":"Ada","lastName":"Lovelace"}'
kill %1
```
Expected: same `{"status":"ok"}` and `201`-with-`userId` results — this proves the app boots and serves correctly under the same command the container's `CMD` uses (just on a different port to avoid clashing with any locally running instance), even though the Docker layer itself isn't exercised. Note in your report which verification path was used and why.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml README.md
git commit -m "feat: add docker-compose.yml and document Docker usage in README"
```

---

## Task 4: Remove resolved gaps from `OpenPoints.md`, add Docker-install open point

**Files:**
- Modify: `OpenPoints.md`

**Interfaces:** None — documentation only. This task runs after Tasks 1–3 land, per the user's explicit "post implementation" instruction. It has two parts: the backlog-hygiene removal of resolved gaps, and a new open point (added because Docker was not installed in this development environment, so Tasks 2–3's Docker-specific verification steps had to fall back to non-Docker proxies instead of an actual `docker build`/`docker compose up` run).

- [ ] **Step 1: Remove the three resolved bullets from the "## Validation gaps" section**

Current section (for reference — do not copy this into the file, it's what you're replacing):
```markdown
## Validation gaps
- ~~Assigning a task to a user in `Task-Group-Relationship` does not verify
  the assignee is actually a member of the target group~~ — **Fixed.**
  `TaskGroupService.assign` now calls `UserGroupService.is_member` and
  raises `BadRequestError(ErrorCode.ASSIGNEE_NOT_GROUP_MEMBER)` (HTTP 400,
  `ERR_TASKS_001`) if the assignee isn't a member of the group.
- ~~Task state transitions (`TaskState`) are unrestricted~~ — **Partially
  fixed.** `TaskService.update_task_state` now rejects moving `COMPLETED` →
  `COMPLETED` again (`BadRequestError(ErrorCode.TASK_ALREADY_COMPLETED)`,
  HTTP 400, `ERR_TASKS_002`). All other transitions, including moving out of
  `COMPLETED` back to `TODO`/`IN-PROGRESS`, remain unrestricted — this was a
  deliberate scope decision, not an oversight; revisit if the product needs
  a full state machine.
- ~~No uniqueness check preventing the same user being added to the same
  group twice~~ — **Fixed.** `UserGroupService.associate` now calls
  `is_member` first and raises
  `BadRequestError(ErrorCode.DUPLICATE_GROUP_MEMBERSHIP)` (HTTP 400,
  `ERR_TASKS_003`) if the user is already associated with the group.
- `PATCH /api/v1/tasks/{task_id}/due-date` requires a `taskDueDate` value
  (`TaskDueDateUpdateRequest.taskDueDate: datetime`, not `Optional`), so
  there is currently no way to clear a task's due date back to `null` via
  the API — even though `Task.taskDueDate` on the domain model itself is
  `Optional[datetime]`.

### Error codes
All three fixes above raise `app.exceptions.BadRequestError`, which routers
translate to HTTP 400 with a JSON body of the form
`{"detail": {"errorCode": "ERR_TASKS_00N", "message": "..."}}`. See
`app.exceptions.ErrorCode` and `ERROR_CODE_MESSAGES` for the current code ->
message mapping:

| Code | Meaning |
|---|---|
| `ERR_TASKS_001` | Assignee is not a member of the target group |
| `ERR_TASKS_002` | Task is already COMPLETED and cannot be marked COMPLETED again |
| `ERR_TASKS_003` | User is already associated with this group |
```

Replace the entire section with (removes all three resolved bullets — including the state-transition one, whose remaining behavior is a deliberate design choice rather than an open gap — keeps the still-open due-date bullet, and keeps the Error codes reference table with its intro reworded since it can no longer refer to "the three fixes above"):

```markdown
## Validation gaps
- `PATCH /api/v1/tasks/{task_id}/due-date` requires a `taskDueDate` value
  (`TaskDueDateUpdateRequest.taskDueDate: datetime`, not `Optional`), so
  there is currently no way to clear a task's due date back to `null` via
  the API — even though `Task.taskDueDate` on the domain model itself is
  `Optional[datetime]`.

### Error codes
`app.exceptions.BadRequestError` is raised by `TaskGroupService.assign`,
`TaskService.update_task_state`, and `UserGroupService.associate` for their
respective validation rules; routers translate it to HTTP 400 with a JSON
body of the form `{"detail": {"errorCode": "ERR_TASKS_00N", "message": "..."}}`.
See `app.exceptions.ErrorCode` and `ERROR_CODE_MESSAGES` for the current
code -> message mapping:

| Code | Meaning |
|---|---|
| `ERR_TASKS_001` | Assignee is not a member of the target group |
| `ERR_TASKS_002` | Task is already COMPLETED and cannot be marked COMPLETED again |
| `ERR_TASKS_003` | User is already associated with this group |
```

- [ ] **Step 2: Add a new "## Deployment" section documenting the missing local Docker install**

Append this new section to the end of `OpenPoints.md` (after the existing "## Testing" section):

```markdown
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
```

- [ ] **Step 3: Verify no other sections in `OpenPoints.md` reference the removed bullets**

Run: `grep -n "Fixed\|Partially fixed" OpenPoints.md`
Expected: no output (both strikethrough/"Fixed" markers are gone; the "Design notes / asymmetries" and other sections are untouched and don't reference these bullets).

- [ ] **Step 4: Run the full test suite (unaffected by a docs-only change, but confirms nothing else broke across all four tasks)**

Run: `pytest -v`
Expected: all 62 tests pass.

- [ ] **Step 5: Commit**

```bash
git add OpenPoints.md
git commit -m "docs: remove resolved validation-gap items, note missing local Docker install"
```

---

## Verification (end-to-end)

1. `pytest -v` — full suite green, 62/62, 0 failures (proves Tasks 1 and 4 didn't regress anything).
2. If Docker is available: `docker compose up --build`, then `curl localhost:8000/health` and a real `POST /api/v1/users` call, then `docker compose down`. If Docker is unavailable (as confirmed in this environment), the per-task fallback verifications (running the same `pip install`/`uvicorn` commands the image would run, directly against `.venv`) stand in as proof the containerized setup would work.
3. `cat requirements.txt` — confirm only 3 runtime packages remain; `cat requirements-dev.txt` — confirm it references `requirements.txt` plus `pytest`/`httpx`.
4. `grep -n "Fixed\|Partially fixed" OpenPoints.md` — confirm no output, i.e. all resolved-gap markers are gone, while the due-date gap and the Error codes reference table remain.
5. `grep -n "Docker is not installed" OpenPoints.md` — confirm the new "## Deployment" open point was added.
