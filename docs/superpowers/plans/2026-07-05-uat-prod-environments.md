# UAT / PROD Environments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `docker-compose.yml` into environment-agnostic config plus two env files — `.env` (UAT, the default, loaded automatically by `docker compose up`) and `.env.prod` (PROD, selected via `--env-file`) — so the exact same compose file runs either environment with fully isolated containers/volumes.

**Architecture:** `docker-compose.yml`'s hardcoded Postgres credentials and port become `${VAR}` substitutions. `.env` carries today's exact values (UAT = current setup, unchanged). `.env.prod` carries distinct placeholder values. Both set `COMPOSE_PROJECT_NAME` so Compose scopes each environment's containers/network/volume separately (otherwise it defaults to the directory name regardless of which env file loads, silently mixing UAT and PROD data).

**Tech Stack:** Docker Compose variable substitution (`${VAR}` syntax, no new tooling). No application code changes.

## Global Constraints

- Config-only difference between UAT and PROD — no environment-conditional application code (confirmed in the approved design).
- Firebase credentials stay a single shared, build-time-baked file for both environments — out of scope (separate, pre-existing open point in `OpenPoints.md`).
- `Dockerfile` is unchanged.
- Neither `.env` nor `.env.prod` holds a real secret — both are committed to git, with `.env.prod` carrying an explicit comment that real production secrets must never be edited into this file directly.
- Docker is not installed in this development environment — every verification step needs a non-Docker fallback proving the same values/commands work, mirroring the pattern used in the prior two Docker-related plans.

---

## Task 1: Parameterize `docker-compose.yml` and add `.env` (UAT)

**Files:**
- Modify: `docker-compose.yml`
- Create: `.env`

**Interfaces:** None — no new Python symbols. Compose reads `${VAR}` placeholders from whichever env file is active at `docker compose` invocation time.

- [ ] **Step 1: Update `docker-compose.yml`**

Current content:
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

Replace with:
```yaml
services:
  db:
    image: postgres:17-alpine
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s
      timeout: 3s
      retries: 5

  api:
    build: .
    ports:
      - "${API_PORT}:8000"
    environment:
      DATABASE_URL: postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}
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

- [ ] **Step 2: Create `.env`**

```
# UAT environment — the default, loaded automatically by `docker compose`
# with no --env-file flag. These are the same values docker-compose.yml
# hardcoded before the UAT/PROD split; no real secrets here.
COMPOSE_PROJECT_NAME=tasknest_uat
POSTGRES_USER=tasknest
POSTGRES_PASSWORD=tasknest
POSTGRES_DB=tasknest_db
API_PORT=8000
```

- [ ] **Step 3: Verify `.env` covers every variable `docker-compose.yml` references**

```bash
python3 -c "
def parse_env_file(path):
    values = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            key, _, value = line.partition('=')
            values[key.strip()] = value.strip()
    return values

required = {'POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_DB', 'API_PORT', 'COMPOSE_PROJECT_NAME'}
uat = parse_env_file('.env')
missing = required - uat.keys()
assert not missing, f'UAT .env missing: {missing}'
assert uat['POSTGRES_USER'] == 'tasknest'
assert uat['POSTGRES_DB'] == 'tasknest_db'
assert uat['API_PORT'] == '8000'
print('OK: .env defines all required variables with the expected UAT (current-setup) values')
"
```
Expected: prints `OK: .env defines all required variables with the expected UAT (current-setup) values`, exit code 0.

- [ ] **Step 4: Verify UAT's derived `DATABASE_URL` still works end-to-end against a real throwaway database**

This re-proves what Task 1 of the prior Docker plan already proved, this time using the exact values sourced from `.env` rather than hand-typed, to confirm the parameterization didn't change the effective connection string:

```bash
createdb tasknest_uat_verify
export DATABASE_URL="postgresql+psycopg://tasknest:tasknest@localhost:5432/tasknest_uat_verify"
source .venv/bin/activate
alembic upgrade head
```
Expected: both migrations apply (`f24972e8b68b`, then `b86979a31d5a`), exit code 0.

```bash
dropdb tasknest_uat_verify
```

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml .env
git commit -m "feat: parameterize docker-compose.yml, add .env for UAT (default) environment"
```

---

## Task 2: Add `.env.prod` (PROD)

**Files:**
- Create: `.env.prod`

**Interfaces:**
- Consumes: Task 1's parameterized `docker-compose.yml` (no changes needed to it — it already reads whichever env file is active).

- [ ] **Step 1: Create `.env.prod`**

```
# PROD environment — selected explicitly via:
#   docker compose --env-file .env.prod up --build
# These are placeholder values, not real secrets. A real production
# deployment must inject real credentials through a proper secrets
# mechanism (CI secret store, secrets manager) — never edit real
# secrets into this file.
COMPOSE_PROJECT_NAME=tasknest_prod
POSTGRES_USER=tasknest_prod
POSTGRES_PASSWORD=change-me-in-real-prod
POSTGRES_DB=tasknest_prod_db
API_PORT=8000
```

- [ ] **Step 2: Verify `.env.prod` covers every required variable and differs from `.env` where it matters**

```bash
python3 -c "
def parse_env_file(path):
    values = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            key, _, value = line.partition('=')
            values[key.strip()] = value.strip()
    return values

required = {'POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_DB', 'API_PORT', 'COMPOSE_PROJECT_NAME'}
uat = parse_env_file('.env')
prod = parse_env_file('.env.prod')
missing = required - prod.keys()
assert not missing, f'PROD .env.prod missing: {missing}'
assert prod['COMPOSE_PROJECT_NAME'] != uat['COMPOSE_PROJECT_NAME'], 'UAT and PROD must not share a Compose project name'
assert prod['POSTGRES_DB'] != uat['POSTGRES_DB'], 'UAT and PROD must not share a database name'
print('OK: .env.prod defines all required variables and is isolated from .env')
"
```
Expected: prints `OK: .env.prod defines all required variables and is isolated from .env`, exit code 0.

- [ ] **Step 3: Verify PROD's derived `DATABASE_URL` works end-to-end against a real throwaway role+database**

Docker isn't installed here, so prove the exact connection string PROD's config produces actually works, using a dedicated Postgres role (not just a database) so the credentials themselves — not only the DB name — are exercised:

```bash
psql postgres -c "CREATE ROLE tasknest_prod WITH LOGIN PASSWORD 'change-me-in-real-prod';"
createdb -O tasknest_prod tasknest_prod_db_verify
export DATABASE_URL="postgresql+psycopg://tasknest_prod:change-me-in-real-prod@localhost:5432/tasknest_prod_db_verify"
source .venv/bin/activate
alembic upgrade head
```
Expected: both migrations apply cleanly, exit code 0. If this fails with an authentication error, check `pg_hba.conf`'s auth method for local TCP connections (`psql -h localhost` specifically, not the Unix socket) — Homebrew's default Postgres 17 install typically trusts local connections already; if not, this is a local-environment quirk to note in the task report, not a bug in `.env.prod` itself.

- [ ] **Step 4: Clean up the throwaway role and database**

```bash
dropdb tasknest_prod_db_verify
psql postgres -c "DROP ROLE tasknest_prod;"
```

- [ ] **Step 5: Commit**

```bash
git add .env.prod
git commit -m "feat: add .env.prod for PROD environment"
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

API available at http://localhost:8000 (Swagger UI at /docs). Postgres now
runs as its own `db` service (named volume `pgdata` persists data across
restarts), and the `api` service runs `alembic upgrade head` automatically
before starting — no manual database setup needed. The image installs only
`requirements.txt` (no test tooling) and runs a single Uvicorn worker.
```

Replace with:
```markdown
## Docker

Two environments, same image, different config via env files:

    docker compose up --build                        # UAT (default)
    docker compose --env-file .env.prod up --build    # PROD

API available at http://localhost:8000 (Swagger UI at /docs) either way.
Postgres runs as its own `db` service (named volume `pgdata` persists data
across restarts), and the `api` service runs `alembic upgrade head`
automatically before starting — no manual database setup needed. `.env`
(UAT) and `.env.prod` (PROD) hold placeholder values only, not real
secrets — each sets `COMPOSE_PROJECT_NAME` so the two environments get
fully isolated containers/volumes even when run on the same machine. The
image installs only `requirements.txt` (no test tooling) and runs a single
Uvicorn worker.
```

- [ ] **Step 2: Update `OpenPoints.md`'s Persistence section**

Find this bullet:
```markdown
- `docker-compose.yml` now runs Postgres as its own `db` service
  (`postgres:17-alpine`, named volume `pgdata`), with the `api` service
  running `alembic upgrade head` automatically on container start. Local
  (non-Docker) development still targets the Postgres 17 instance installed
  via Homebrew (`brew services start postgresql@17`).
```

Replace with:
```markdown
- `docker-compose.yml` runs Postgres as its own `db` service
  (`postgres:17-alpine`, named volume `pgdata`), with the `api` service
  running `alembic upgrade head` automatically on container start.
  Credentials/DB name/port are parameterized via `${VAR}` substitution, not
  hardcoded — `.env` (UAT, the default) and `.env.prod` (PROD, via
  `docker compose --env-file .env.prod up`) supply the values, each with
  its own `COMPOSE_PROJECT_NAME` so the two environments' containers and
  volumes stay isolated. Neither file holds a real secret. Local
  (non-Docker) development still targets the Postgres 17 instance installed
  via Homebrew (`brew services start postgresql@17`).
```

- [ ] **Step 3: Add a note to `OpenPoints.md`'s Deployment section**

Find the Firebase credentials bullet (the second bullet in Deployment,
about `app/firebase/firebase-adminsdk.json`) and add this new bullet
immediately after it:

```markdown
- UAT and PROD environments (`.env` / `.env.prod`) currently only vary
  Postgres credentials/DB name/port — both still share the single
  build-time-baked Firebase credentials file (see the bullet above). If
  UAT and PROD ever need separate Firebase projects, that requires solving
  the credentials-injection gap first (mounting the credentials file at
  runtime instead of `COPY`-ing it at build time), which isn't done here.
```

- [ ] **Step 4: Run the full test suite (unaffected by this change, confirms no regression)**

Run: `.venv/bin/pytest -v`
Expected: all tests pass (177, matching the count before this change), 0 failures.

- [ ] **Step 5: Commit**

```bash
git add README.md OpenPoints.md
git commit -m "docs: describe the UAT/PROD docker-compose environment split"
```

---

## Verification (end-to-end)

1. `.venv/bin/pytest -v` — full suite green, 177/177, 0 failures.
2. Task 1's Steps 3-4 (`.env` variable-coverage check + UAT throwaway-DB migration) pass.
3. Task 2's Steps 2-3 (`.env.prod` variable-coverage/isolation check + PROD throwaway-role-and-DB migration) pass.
4. `cat docker-compose.yml` — confirm every previously-hardcoded value is now a `${VAR}` substitution, no leftover literal `tasknest`/`8000` credentials.
5. `cat .env .env.prod` — confirm both exist, both define all 5 variables, and `COMPOSE_PROJECT_NAME`/`POSTGRES_DB` differ between them.
6. If Docker is available when this plan is executed: `docker compose up --build` (confirm UAT values via `docker compose exec api env | grep POSTGRES_DB` → `tasknest_db`), tear down, then `docker compose --env-file .env.prod up --build` (confirm PROD values → `tasknest_prod_db`), and `docker compose ls` showing `tasknest_uat`/`tasknest_prod` as separate projects if both were left running.
