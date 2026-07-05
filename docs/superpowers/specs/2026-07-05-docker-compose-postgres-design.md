# Docker Compose Postgres Service — Design

## Context

`docker-compose.yml` currently defines only the `api` service. Per
`OpenPoints.md`'s Persistence section, it "does not run Postgres — local
development targets the Postgres 17 instance installed via Homebrew," and
the README's Docker section explicitly warns that the containerized `api`
needs a reachable `DATABASE_URL` supplied externally (e.g. pointing at the
host's local Postgres) for it to actually connect. This means `docker
compose up --build` alone does not produce a working stack today — the app
now that it's fully Postgres-backed (per the `2026-07-03` Docker plan's
follow-on migration to Postgres) has no database to talk to unless the
developer already has one running and wires up `DATABASE_URL` by hand.

Goal: make `docker compose up --build` alone produce a fully working,
migrated API with zero manual DB setup.

## Design

**`docker-compose.yml`** gains a `db` service:

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

`db` uses a named volume so data survives `docker compose down` (without
`-v`) and restarts. The healthcheck gates `api`'s startup so the app never
races Postgres's boot.

**Credentials**: hardcoded directly in the compose file (`tasknest` /
`tasknest` / `tasknest_db`), matched between the two services. This is a
local/dev-only compose file — the repo has no production secrets or
deployment target defined anywhere else — so a `.env` file or secrets
manager would be premature indirection for 3 duplicated values in one file.

**`Dockerfile`** changes: add `COPY migrations/ migrations/` and `COPY
alembic.ini .` (currently only `app/` is copied in); no new dependency,
`alembic==1.14.0` is already in `requirements.txt`. The `CMD` changes from
`["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]` to a
shell form that runs migrations first:

```dockerfile
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
```

Migrations run automatically and idempotently on every container start —
Alembic tracks applied revisions in an `alembic_version` table, so re-running
`upgrade head` against an already-migrated DB is a no-op.

**`.dockerignore`**: no change needed — it excludes `*.md` but not
`migrations/` or `alembic.ini`, so both are already includable in the build
context; only the `Dockerfile`'s `COPY` lines were missing them.

## Docs to update

- **README.md** "## Docker" section: remove the "does not run Postgres...
  needs a reachable `DATABASE_URL`" warning; state that `docker compose up
  --build` now runs Postgres too and migrates automatically.
- **OpenPoints.md** Persistence section: remove/replace the "docker-compose
  does not run Postgres" bullet.
- **OpenPoints.md** Deployment section: keep the existing "Docker not
  installed on this development machine" caveat (still true — verified via
  `docker --version` failing again during this session) and add a note that
  the new `db` service + auto-migration-on-startup behavior specifically
  needs a real `docker compose up --build` run to confirm once Docker is
  available, since it could only be verified indirectly this time too.

## Verification (no Docker daemon available in this environment)

Same fallback approach as the original Docker setup plan
(`docs/superpowers/plans/2026-07-03-tasknest-docker-compose.md`): prove the
exact commands the container will run actually work, directly against the
local Homebrew Postgres 17 instance, using a throwaway database so nothing
touches the real dev DB:

1. Create a throwaway Postgres database and point `DATABASE_URL` at it.
2. Run `alembic upgrade head` against it — confirm both existing migrations
   apply cleanly to a brand-new empty database (proving the exact `CMD`
   step works, and incidentally proving the two committed migrations are
   still valid against a fresh schema, not just incrementally-applied
   ones).
3. Run `alembic upgrade head` a second time — confirm it's a no-op (proving
   the "runs on every container start" idempotency claim).
4. Start `uvicorn` against that same throwaway DB and hit `/health` plus a
   real `POST /api/v1/users` call, confirming the app works end-to-end
   against a database that only Alembic (not any manual schema setup)
   touched.
5. Drop the throwaway database.
6. Run the full existing `pytest -v` suite unchanged (it uses its own
   `tasks_net_db_test` database per `tests/conftest.py` — unaffected by
   this change) to confirm no regression.

If Docker happens to be available when this plan is executed, additionally
run `docker compose up --build`, `curl localhost:8000/health`, a `POST
/api/v1/users` call, and `docker compose down`, per the original plan's
pattern.

## Out of scope

- Firebase credentials-at-build-time (already a known, separate open point
  in `OpenPoints.md`'s Deployment section — not touched here).
- A test-database service in compose (tests remain local-only per the
  existing, explicitly-confirmed constraint from the original Docker plan).
- `.env`-based credential overrides (see Credentials above).
