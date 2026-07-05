# Docker Compose Postgres Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `docker compose up --build` alone produce a fully working, auto-migrated TaskNest API, by adding a `db` (Postgres) service to `docker-compose.yml` and running Alembic migrations automatically on container startup.

**Architecture:** `docker-compose.yml` gains a `postgres:17-alpine` `db` service with a named volume for persistence and a `pg_isready` healthcheck; the `api` service gains a `DATABASE_URL` pointing at `db:5432`, a `depends_on: db: condition: service_healthy` gate, and its container's `CMD` runs `alembic upgrade head` before `uvicorn` starts. `Dockerfile` is extended to copy `migrations/` and `alembic.ini` into the image (previously only `app/` was copied).

**Tech Stack:** Docker Compose (Compose Spec), `postgres:17-alpine` image, Alembic (already a runtime dependency — `alembic==1.14.0` in `requirements.txt`). No new Python dependencies.

## Global Constraints

- Credentials are hardcoded directly in `docker-compose.yml` (`tasknest`/`tasknest`/`tasknest_db`) — this is a local/dev-only compose file, no `.env` file, confirmed in the approved design (`docs/superpowers/specs/2026-07-05-docker-compose-postgres-design.md`).
- No test-runner service or test-database service is added to `docker-compose.yml` — tests remain local-only, per the original Docker plan's confirmed constraint (still applies).
- Docker is not installed in this development environment (`docker --version` → command not found, reconfirmed during design). Every task's verification must have a non-Docker fallback that proves the same commands the container would run actually work, run directly against the local Homebrew Postgres 17 instance.
- Firebase credentials-at-build-time and `.env`-based config overrides are explicitly out of scope (see the design doc's "Out of scope" section).

---

## Task 1: Extend `Dockerfile` to include migrations and run them on startup

**Files:**
- Modify: `Dockerfile`

**Interfaces:** None — no new Python symbols. Consumes the existing `migrations/` directory and `alembic.ini` (both already committed, unchanged) and the existing `alembic==1.14.0` entry in `requirements.txt` (already installed by the existing `RUN pip install` step).

- [ ] **Step 1: Update `Dockerfile`**

Current content:
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

Replace with:
```dockerfile
FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY migrations/ migrations/
COPY alembic.ini .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
```

- [ ] **Step 2: Verify migrations apply cleanly and idempotently against a fresh database**

Docker isn't installed here, so prove the exact `alembic upgrade head` command the new `CMD` runs actually works, against a brand-new throwaway Postgres database (so this also proves the two already-committed migrations are valid against an empty schema, not just incrementally-applied ones):

```bash
createdb tasknest_docker_verify
export DATABASE_URL="postgresql+psycopg://ranjith@localhost:5432/tasknest_docker_verify"
source .venv/bin/activate
alembic upgrade head
```
Expected: Alembic logs applying both revisions in order (`f24972e8b68b` then `b86979a31d5a`), ending with `INFO  [alembic.runtime.migration] Running upgrade f24972e8b68b -> b86979a31d5a, add group_id to tasks`, exit code 0.

- [ ] **Step 3: Verify re-running migrations is a no-op (idempotency)**

```bash
alembic upgrade head
```
Expected: exits 0 with no "Running upgrade" lines printed — Alembic sees `alembic_version` already at head and does nothing. This proves the container is safe to restart repeatedly without re-applying anything.

- [ ] **Step 4: Verify the app boots and can actually read/write against the freshly-migrated schema**

Since the app now requires a valid Firebase ID token for any `POST` endpoint (which we can't produce outside pytest's dependency override), verify the ORM/repository layer directly instead of via HTTP — this proves the migration produced a schema the app's own code can actually use:

```bash
python3 -c "
import os
os.environ['DATABASE_URL'] = 'postgresql+psycopg://ranjith@localhost:5432/tasknest_docker_verify'
import uuid
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.repositories.user_repository import UserRepository
from app.models.user import Name, User
from app.models.enums import UserStatus

engine = create_engine(os.environ['DATABASE_URL'])
Session = sessionmaker(bind=engine)
session = Session()
repo = UserRepository(session)
user = User(
    userId=str(uuid.uuid4()),
    name=Name(firstName='Ada', lastName='Lovelace'),
    userStatus=UserStatus.ACTIVE,
    createdAt=datetime.now(timezone.utc),
)
repo.add(user)
session.commit()
fetched = repo.get(user.userId)
assert fetched is not None
assert fetched.name.firstName == 'Ada'
print('OK: insert+fetch against freshly migrated DB succeeded')
"
```
Expected: prints `OK: insert+fetch against freshly migrated DB succeeded`, exit code 0.

Also confirm `/health` boots correctly under the exact `uvicorn` invocation the new `CMD` uses:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8001 &
sleep 1
curl -s localhost:8001/health
kill %1
```
Expected: `{"status":"ok"}`.

- [ ] **Step 5: Clean up the throwaway database**

```bash
dropdb tasknest_docker_verify
```

- [ ] **Step 6: Commit**

```bash
git add Dockerfile
git commit -m "feat: copy migrations into the image and run alembic upgrade head on container start"
```

---

## Task 2: Add a `db` service to `docker-compose.yml`

**Files:**
- Modify: `docker-compose.yml`

**Interfaces:**
- Consumes: Task 1's updated `Dockerfile` (via `api`'s existing `build: .`).
- Produces: the `db` service hostname (`db`) and port (`5432`) that `api`'s `DATABASE_URL` connects to; the `pgdata` named volume.

- [ ] **Step 1: Update `docker-compose.yml`**

Current content:
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

Replace with:
```yaml
services:
  db:
    image: postgres:17-alpine
    environment:
      POSTGRES_USER: tasknest
      POSTGRES_PASSWORD: tasknest
      POSTGRES_DB: tasknest_db
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U tasknest -d tasknest_db"]
      interval: 5s
      timeout: 3s
      retries: 5

  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql+psycopg://tasknest:tasknest@db:5432/tasknest_db
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 3s
      start_period: 5s
      retries: 3

volumes:
  pgdata:
```

- [ ] **Step 2: Verify the YAML is syntactically valid**

Docker isn't installed here, so `docker compose config` can't run — validate the YAML parses correctly and has the expected shape instead:

```bash
python3 -c "
import yaml
with open('docker-compose.yml') as f:
    doc = yaml.safe_load(f)
assert set(doc['services']) == {'db', 'api'}
assert doc['services']['db']['image'] == 'postgres:17-alpine'
assert doc['services']['api']['depends_on']['db']['condition'] == 'service_healthy'
assert doc['services']['api']['environment']['DATABASE_URL'] == 'postgresql+psycopg://tasknest:tasknest@db:5432/tasknest_db'
assert 'pgdata' in doc['volumes']
print('OK: docker-compose.yml is valid YAML with the expected services/volumes')
"
```
Expected: prints `OK: docker-compose.yml is valid YAML with the expected services/volumes`, exit code 0. (`pyyaml` is already available — it's a transitive dependency of other installed packages; if the import fails, run `pip install pyyaml` in `.venv` first since it's only needed for this one-off verification, not a project dependency.)

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add Postgres db service to docker-compose.yml"
```

---

## Task 3: Update docs and run full regression

**Files:**
- Modify: `README.md`
- Modify: `OpenPoints.md`

**Interfaces:** None — documentation only.

- [ ] **Step 1: Update README.md's "## Docker" section**

Current content:
```markdown
## Docker

docker compose up --build

API available at http://localhost:8000 (Swagger UI at /docs). The image
installs only `requirements.txt` (no test tooling) and runs a single
Uvicorn worker. Note: `docker-compose.yml` does not run Postgres — the
containerized `api` service needs a reachable `DATABASE_URL` (e.g.
pointing at the host's local Postgres) to actually connect, see
`OpenPoints.md`.
```

Replace with:
```markdown
## Docker

docker compose up --build

API available at http://localhost:8000 (Swagger UI at /docs). Postgres now
runs as its own `db` service (named volume `pgdata` persists data across
restarts), and the `api` service runs `alembic upgrade head` automatically
before starting — no manual database setup needed. The image installs only
`requirements.txt` (no test tooling) and runs a single Uvicorn worker.
```

- [ ] **Step 2: Update `OpenPoints.md`'s Persistence section**

Find this bullet:
```markdown
- `docker-compose.yml` does not run Postgres — local development targets
  the Postgres 17 instance installed via Homebrew (`brew services start
  postgresql@17`). Revisit if/when this needs to run in Docker.
```

Replace with:
```markdown
- `docker-compose.yml` now runs Postgres as its own `db` service
  (`postgres:17-alpine`, named volume `pgdata`), with the `api` service
  running `alembic upgrade head` automatically on container start. Local
  (non-Docker) development still targets the Postgres 17 instance installed
  via Homebrew (`brew services start postgresql@17`).
```

- [ ] **Step 3: Update `OpenPoints.md`'s Deployment section**

Find this bullet (the first one, about Docker not being installed):
```markdown
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

Replace with:
```markdown
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
```

- [ ] **Step 4: Run the full test suite (unaffected by this change, confirms no regression)**

Run: `.venv/bin/pytest -v`
Expected: all tests pass (177 as of the last count in this repo — confirm the exact number printed matches what `pytest -v` reports before this change, i.e. no new failures and no tests lost).

- [ ] **Step 5: Commit**

```bash
git add README.md OpenPoints.md
git commit -m "docs: describe the new docker-compose Postgres service and auto-migration"
```

---

## Verification (end-to-end)

1. `.venv/bin/pytest -v` — full suite green, same count as before this change (177), 0 failures.
2. Task 1's Steps 2-4 (throwaway-DB migration + insert/fetch + `/health`) all pass.
3. Task 2's Step 2 (YAML structural check) passes.
4. `cat docker-compose.yml` — confirm `db` and `api` services both present, `api` has `DATABASE_URL` and `depends_on: db: condition: service_healthy`, a top-level `volumes: pgdata:` exists.
5. `cat Dockerfile` — confirm `COPY migrations/ migrations/`, `COPY alembic.ini .`, and the new shell-form `CMD` are present.
6. If Docker is available when this plan is executed: `docker compose up --build`, then `curl localhost:8000/health`, then `docker compose exec db psql -U tasknest -d tasknest_db -c '\dt'` to confirm all 5 tables exist, then `docker compose down`.
