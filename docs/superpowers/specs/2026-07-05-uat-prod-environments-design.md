# UAT / PROD Environments — Design

## Context

`docker-compose.yml` currently hardcodes one set of Postgres credentials
(`tasknest`/`tasknest`/`tasknest_db`) directly in the file, with no concept
of "which environment am I running." The user wants two environments —
UAT and PROD — where UAT is exactly today's setup (the default, run with
`docker compose up --build`, no extra flags), and PROD is a separate,
explicitly-selected config profile. The app itself has no
environment-conditional behavior (no feature flags, no env-based
branching) — only `DATABASE_URL` and `FIREBASE_CREDENTIALS_PATH` are
configurable today — so per the approved decision, the two environments
differ only in **config values**, not in code or infrastructure shape.

## Design

**`docker-compose.yml`** becomes environment-agnostic — parameterized via
Compose variable substitution instead of hardcoded values:

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

**`.env`** (UAT — loaded automatically by `docker compose` when no
`--env-file` is given, so this is the default/no-flag path):

```
COMPOSE_PROJECT_NAME=tasknest_uat
POSTGRES_USER=tasknest
POSTGRES_PASSWORD=tasknest
POSTGRES_DB=tasknest_db
API_PORT=8000
```

These are the exact values `docker-compose.yml` hardcoded before this
change — "map current setup to UAT" means UAT *is* today's setup, unchanged.

**`.env.prod`** (PROD — selected explicitly via `--env-file`):

```
COMPOSE_PROJECT_NAME=tasknest_prod
POSTGRES_USER=tasknest_prod
POSTGRES_PASSWORD=change-me-in-real-prod
POSTGRES_DB=tasknest_prod_db
API_PORT=8000
```

Both files set `COMPOSE_PROJECT_NAME`. Compose derives container, network,
and volume names from the project name, which otherwise defaults to the
current directory name regardless of which env file is loaded — without
this, running PROD via `--env-file .env.prod` after UAT would reuse UAT's
exact containers and the same `pgdata` volume under PROD's credentials,
silently mixing data between environments. Setting it explicitly per file
gives each environment fully isolated containers/network/volumes for free.

Neither file holds a real secret — `tasknest`/`tasknest_prod` are
placeholders, same spirit as the existing hardcoded UAT values. Both are
committed to git (not `.gitignore`d), with a comment at the top of
`.env.prod` making explicit that a real production deployment must inject
real secrets through a proper mechanism (CI secret store, secrets manager)
rather than editing this file in place.

## How to run each

- **UAT (default):** `docker compose up --build` — no flag needed, Compose
  auto-loads `.env`.
- **PROD:** `docker compose --env-file .env.prod up --build`.

## Out of scope

- Firebase credentials remain a single shared, build-time-baked file for
  both environments (already a separately-tracked open point in
  `OpenPoints.md`'s Deployment section — giving each environment its own
  Firebase project would require solving the credentials-injection gap
  there first: runtime mount instead of build-time `COPY`).
- `Dockerfile` is unchanged — it's unaffected by which env file `docker
  compose` loads at runtime; only `docker-compose.yml` and the new env
  files are in scope.
- No new environment-conditional application code (logging levels, worker
  counts, etc.) — matches the approved "config only" scope.

## Docs to update

- **README.md** "## Docker" section: document both commands (UAT default,
  PROD explicit `--env-file`) and that `.env`/`.env.prod` hold placeholder
  values only.
- **OpenPoints.md** Persistence/Deployment sections: note the environment
  split, the `COMPOSE_PROJECT_NAME` isolation mechanism, and that
  `.env.prod`'s values are placeholders requiring real secret injection
  before any actual production use.

## Verification (no Docker daemon available in this environment)

Same non-Docker fallback pattern as the prior Docker-related plans:

1. Write a small Python script that parses `.env` and `.env.prod` (simple
   `KEY=VALUE` parser, no library needed) and confirms every
   `${VAR}`-style placeholder used in `docker-compose.yml`
   (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `API_PORT`) has a
   value defined in both files, and that `COMPOSE_PROJECT_NAME` differs
   between them.
2. Manually construct the `DATABASE_URL` each environment would produce
   from its own `.env`/`.env.prod` values, and for `.env.prod`'s
   values specifically (since UAT's were already verified against a real
   throwaway DB in the prior plan): create a throwaway Postgres **role**
   matching `.env.prod`'s exact `POSTGRES_USER`/`POSTGRES_PASSWORD` plus a
   throwaway **database** owned by that role matching `POSTGRES_DB`, run
   `alembic upgrade head` against it using the exact resulting
   `DATABASE_URL` string, confirm it applies cleanly, then drop both the
   throwaway database and role.
3. Run the full existing `pytest -v` suite unchanged, to confirm no
   regression (it doesn't touch `docker-compose.yml` or the new env files
   at all).

If Docker is available when this plan is executed, additionally run
`docker compose up --build` (confirm it uses UAT values with no flag) and
`docker compose --env-file .env.prod up --build` (confirm PROD values,
and that `docker compose ls` shows two separate, isolated projects), then
tear both down.
