# Firebase ID Token Authentication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Require a valid `Authorization: Bearer <Firebase_ID_Token>` header on every TaskNest endpoint except `POST /api/v1/users`, verified via the firebase-admin SDK, returning 401 on anything invalid.

**Architecture:** A single new module, `app/auth.py`, exposes one FastAPI dependency (`verify_firebase_token`) that parses the header and calls `firebase_admin.auth.verify_id_token`. It's wired in at the router level for the 4 fully-protected router files and per-route for the 3 non-create routes in `users.py`. Existing tests keep passing unchanged because the shared `client` fixture in `tests/conftest.py` overrides this one new dependency alongside the service-level overrides it already does.

**Tech Stack:** `firebase-admin` (Python SDK), FastAPI `Depends`/`Header`, pytest + `unittest.mock`.

## Global Constraints

- Protect every route except `POST /api/v1/users` (`create_user`), per `ASK.md`.
- Header format exactly `Authorization: Bearer <Firebase_ID_Token>`, per `ASK.md`.
- Credential file path: `app/firebase/firebase-adminsdk.json`, per `ASK.md`.
- **Security**: this file contains a real private key and is currently untracked but NOT gitignored — Task 1 must land before any other commit in this plan.
- No test may call real Firebase — all Firebase interaction in tests is mocked or bypassed via `app.dependency_overrides`.
- This pass is authentication only — no authorization/ownership enforcement (confirmed with the user). Document this explicitly in `OpenPoints.md` (Task 4).

---

## Task 1: Gitignore the Firebase credential (security fix — do this first)

**Files:**
- Modify: `.gitignore`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing later tasks depend on directly, but this MUST land before Task 2's commit touches anything else, so the credential file is never at risk of being swept into a commit.

- [ ] **Step 1: Add the ignore rule**

In `.gitignore`, change:
```
.venv/
__pycache__/
*.pyc
.pytest_cache/
```
to:
```
.venv/
__pycache__/
*.pyc
.pytest_cache/

# Firebase service-account credentials (secret, never commit)
app/firebase/
```

- [ ] **Step 2: Verify it's actually ignored**

Run: `git status`
Expected: `app/firebase/` no longer appears under "Untracked files".

Run: `git check-ignore -v app/firebase/firebase-adminsdk.json`
Expected: prints a match (e.g. `.gitignore:6:app/firebase/	app/firebase/firebase-adminsdk.json`) — a non-empty match confirms the file is ignored; no output would mean it is NOT ignored (stop and re-check the pattern if so).

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: gitignore the Firebase service-account credential file"
```

---

## Task 2: Firebase auth utility module

**Files:**
- Modify: `requirements.txt`
- Create: `app/auth.py`
- Create: `tests/unit/test_auth.py`

**Interfaces:**
- Consumes: `app/firebase/firebase-adminsdk.json` (existing file, now gitignored per Task 1).
- Produces: `verify_firebase_token(authorization: str | None = Header(None)) -> str` — a FastAPI dependency that raises `HTTPException(401)` on any invalid/missing/malformed auth, or returns the Firebase `uid` string on success. Task 3 wires this into every router.

- [ ] **Step 1: Add the dependency**

In `requirements.txt`, change:
```
fastapi==0.115.6
uvicorn[standard]==0.34.0
pydantic==2.10.4
sqlalchemy==2.0.36
psycopg[binary]==3.2.3
alembic==1.14.0
```
to:
```
fastapi==0.115.6
uvicorn[standard]==0.34.0
pydantic==2.10.4
sqlalchemy==2.0.36
psycopg[binary]==3.2.3
alembic==1.14.0
firebase-admin==7.5.0
```

- [ ] **Step 2: Install and verify**

Run: `.venv/bin/pip install -r requirements.txt`
Run: `.venv/bin/python -c "import firebase_admin; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Write the failing unit tests**

Create `tests/unit/test_auth.py`:
```python
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.auth import verify_firebase_token


def test_missing_header_raises_401():
    with pytest.raises(HTTPException) as exc_info:
        verify_firebase_token(authorization=None)
    assert exc_info.value.status_code == 401


def test_wrong_scheme_raises_401():
    with pytest.raises(HTTPException) as exc_info:
        verify_firebase_token(authorization="Basic abc123")
    assert exc_info.value.status_code == 401


def test_bearer_with_empty_token_raises_401():
    with pytest.raises(HTTPException) as exc_info:
        verify_firebase_token(authorization="Bearer ")
    assert exc_info.value.status_code == 401


def test_invalid_token_raises_401():
    with patch("app.auth.auth.verify_id_token", side_effect=ValueError("bad token")):
        with pytest.raises(HTTPException) as exc_info:
            verify_firebase_token(authorization="Bearer some-token")
    assert exc_info.value.status_code == 401


def test_valid_token_returns_uid():
    with patch("app.auth.auth.verify_id_token", return_value={"uid": "firebase-uid-123"}):
        result = verify_firebase_token(authorization="Bearer some-token")
    assert result == "firebase-uid-123"
```

- [ ] **Step 4: Run to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.auth'`.

- [ ] **Step 5: Create the module**

Create `app/auth.py`:
```python
import os

import firebase_admin
from fastapi import Header, HTTPException, status
from firebase_admin import auth, credentials

FIREBASE_CREDENTIALS_PATH = os.environ.get(
    "FIREBASE_CREDENTIALS_PATH", "app/firebase/firebase-adminsdk.json"
)

try:
    firebase_admin.get_app()
except ValueError:
    _cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
    firebase_admin.initialize_app(_cred)


def verify_firebase_token(authorization: str | None = Header(None)) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must be in the form 'Bearer <token>'",
        )

    try:
        decoded_token = auth.verify_id_token(token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Firebase ID token",
        ) from exc

    return decoded_token["uid"]
```
Notes: `firebase_admin.get_app()`/`except ValueError` makes the module's
init idempotent (safe to import more than once, e.g. during test
collection). No network call happens at import time — only
`auth.verify_id_token()` on a real request needs network access (to fetch
Google's public certs), so importing this module only requires the
credential file to exist on disk.

- [ ] **Step 6: Run to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_auth.py -v`
Expected: PASS (5 tests). This also proves the credential file at
`app/firebase/firebase-adminsdk.json` is valid JSON that
`credentials.Certificate` can load — if this step fails with a
credential-loading error instead of a test assertion error, stop and
check the file's contents before proceeding.

- [ ] **Step 7: Confirm nothing existing broke**

Run: `.venv/bin/pytest -v`
Expected: PASS — full suite (adding a new, unused-so-far module changes nothing else).

- [ ] **Step 8: Commit**

```bash
git add requirements.txt app/auth.py tests/unit/test_auth.py
git commit -m "feat: add Firebase ID token verification utility"
```

---

## Task 3: Protect every route except create_user

**Files:**
- Modify: `app/api/v1/groups.py`
- Modify: `app/api/v1/user_group.py`
- Modify: `app/api/v1/tasks.py`
- Modify: `app/api/v1/task_group.py`
- Modify: `app/api/v1/users.py`
- Modify: `tests/conftest.py`
- Create: `tests/integration/test_auth_api.py`

**Interfaces:**
- Consumes: `verify_firebase_token` (Task 2).
- Produces: an `unauthenticated_client` pytest fixture (identical wiring to `client` but without overriding auth) — no later task depends on it, it's used only by `test_auth_api.py`.

- [ ] **Step 1: Add the fixtures to `tests/conftest.py`**

Add the import, change the existing `client` fixture, and add a new
`unauthenticated_client` fixture. Change:
```python
from app.dependencies import (
    get_group_service,
    get_task_group_service,
    get_task_service,
    get_user_group_service,
    get_user_service,
)
```
to:
```python
from app.auth import verify_firebase_token
from app.dependencies import (
    get_group_service,
    get_task_group_service,
    get_task_service,
    get_user_group_service,
    get_user_service,
)
```

Change:
```python
    app.dependency_overrides[get_user_service] = lambda: user_service
    app.dependency_overrides[get_group_service] = lambda: group_service
    app.dependency_overrides[get_user_group_service] = lambda: user_group_service
    app.dependency_overrides[get_task_service] = lambda: task_service
    app.dependency_overrides[get_task_group_service] = lambda: task_group_service

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
```
to:
```python
    app.dependency_overrides[get_user_service] = lambda: user_service
    app.dependency_overrides[get_group_service] = lambda: group_service
    app.dependency_overrides[get_user_group_service] = lambda: user_group_service
    app.dependency_overrides[get_task_service] = lambda: task_service
    app.dependency_overrides[get_task_group_service] = lambda: task_group_service
    app.dependency_overrides[verify_firebase_token] = lambda: "test-firebase-uid"

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def unauthenticated_client(db_session):
    user_repo = UserRepository(db_session)
    group_repo = GroupRepository(db_session)
    user_group_repo = UserGroupRepository(db_session)
    task_repo = TaskRepository(db_session)
    task_group_repo = TaskGroupRepository(db_session)

    user_service = UserService(user_repo)
    group_service = GroupService(group_repo, user_service)
    user_group_service = UserGroupService(user_group_repo, user_service, group_service)
    task_service = TaskService(task_repo, user_service)
    task_group_service = TaskGroupService(
        task_group_repo, task_service, group_service, user_service, user_group_service
    )

    app.dependency_overrides[get_user_service] = lambda: user_service
    app.dependency_overrides[get_group_service] = lambda: group_service
    app.dependency_overrides[get_user_group_service] = lambda: user_group_service
    app.dependency_overrides[get_task_service] = lambda: task_service
    app.dependency_overrides[get_task_group_service] = lambda: task_group_service
    # deliberately NOT overriding verify_firebase_token

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
```

- [ ] **Step 2: Run the existing suite to confirm it's still green**

Run: `.venv/bin/pytest tests/unit tests/integration -v`
Expected: PASS — every existing test still passes; the `client` fixture's
new override makes every request transparently "authenticated."

- [ ] **Step 3: Write the failing integration tests**

Create `tests/integration/test_auth_api.py`:
```python
def test_protected_route_without_authorization_header_returns_401(unauthenticated_client):
    response = unauthenticated_client.get("/api/v1/users/some-id")
    assert response.status_code == 401


def test_protected_route_with_malformed_header_returns_401(unauthenticated_client):
    response = unauthenticated_client.get(
        "/api/v1/users/some-id", headers={"Authorization": "Token abc123"}
    )
    assert response.status_code == 401


def test_create_user_without_authorization_header_still_succeeds(unauthenticated_client):
    response = unauthenticated_client.post(
        "/api/v1/users",
        json={"firstName": "Ada", "lastName": "Lovelace"},
    )
    assert response.status_code == 201
```

- [ ] **Step 4: Run to verify they fail**

Run: `.venv/bin/pytest tests/integration/test_auth_api.py -v`
Expected: the first two tests FAIL (both currently return 200/404, not
401, since no route is protected yet); the third already PASSes
(`create_user` never had auth to begin with).

- [ ] **Step 5: Wire the 4 fully-protected routers**

In `app/api/v1/groups.py`, change:
```python
from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_group_service
```
to:
```python
from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import verify_firebase_token
from app.dependencies import get_group_service
```
and change:
```python
router = APIRouter(prefix="/api/v1", tags=["groups"])
```
to:
```python
router = APIRouter(
    prefix="/api/v1", tags=["groups"], dependencies=[Depends(verify_firebase_token)]
)
```

In `app/api/v1/user_group.py`, change:
```python
from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_user_group_service
```
to:
```python
from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import verify_firebase_token
from app.dependencies import get_user_group_service
```
and change:
```python
router = APIRouter(prefix="/api/v1/groups", tags=["user-group"])
```
to:
```python
router = APIRouter(
    prefix="/api/v1/groups",
    tags=["user-group"],
    dependencies=[Depends(verify_firebase_token)],
)
```

In `app/api/v1/tasks.py`, change:
```python
from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_task_service
```
to:
```python
from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import verify_firebase_token
from app.dependencies import get_task_service
```
and change:
```python
router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])
```
to:
```python
router = APIRouter(
    prefix="/api/v1/tasks", tags=["tasks"], dependencies=[Depends(verify_firebase_token)]
)
```

In `app/api/v1/task_group.py`, change:
```python
from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_task_group_service
```
to:
```python
from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import verify_firebase_token
from app.dependencies import get_task_group_service
```
and change:
```python
router = APIRouter(prefix="/api/v1/groups/{group_id}/tasks/{task_id}/assignee", tags=["task-group"])
```
to:
```python
router = APIRouter(
    prefix="/api/v1/groups/{group_id}/tasks/{task_id}/assignee",
    tags=["task-group"],
    dependencies=[Depends(verify_firebase_token)],
)
```

- [ ] **Step 6: Wire `users.py` per-route (skip `create_user`)**

In `app/api/v1/users.py`, change:
```python
from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_user_service
```
to:
```python
from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import verify_firebase_token
from app.dependencies import get_user_service
```

Change:
```python
@router.get(
    "/{user_id}",
    response_model=UserResponse,
    responses={404: {"description": "User not found"}},
)
def get_user(user_id: str, service: UserService = Depends(get_user_service)) -> UserResponse:
```
to:
```python
@router.get(
    "/{user_id}",
    response_model=UserResponse,
    responses={404: {"description": "User not found"}},
    dependencies=[Depends(verify_firebase_token)],
)
def get_user(user_id: str, service: UserService = Depends(get_user_service)) -> UserResponse:
```

Change:
```python
@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    responses={404: {"description": "User not found"}},
)
def update_user(
```
to:
```python
@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    responses={404: {"description": "User not found"}},
    dependencies=[Depends(verify_firebase_token)],
)
def update_user(
```

Change:
```python
@router.patch(
    "/{user_id}/status",
    response_model=UserResponse,
    responses={404: {"description": "User not found"}},
)
def update_user_status(
```
to:
```python
@router.patch(
    "/{user_id}/status",
    response_model=UserResponse,
    responses={404: {"description": "User not found"}},
    dependencies=[Depends(verify_firebase_token)],
)
def update_user_status(
```
(`create_user`'s decorator, lines above `get_user`, is untouched.)

- [ ] **Step 7: Run the new integration tests to verify they pass**

Run: `.venv/bin/pytest tests/integration/test_auth_api.py -v`
Expected: PASS (3 tests).

- [ ] **Step 8: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: PASS — every test, including all pre-existing ones (which
authenticate transparently via the `client` fixture's override) and the 3
new ones (which deliberately bypass that override).

- [ ] **Step 9: Manual smoke test against the real app**

Run: `.venv/bin/uvicorn app.main:app --reload` (confirms `app/auth.py`'s
module-level Firebase init succeeds against the real credential file),
then in another terminal:
```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/api/v1/tasks/some-id
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer garbage" http://127.0.0.1:8000/api/v1/tasks/some-id
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8000/api/v1/users -H "Content-Type: application/json" -d '{"firstName":"Ada","lastName":"Lovelace"}'
```
Expected: `401`, `401`, `201` respectively.

- [ ] **Step 10: Commit**

```bash
git add app/api/v1/groups.py app/api/v1/user_group.py app/api/v1/tasks.py app/api/v1/task_group.py app/api/v1/users.py tests/conftest.py tests/integration/test_auth_api.py
git commit -m "feat: require Firebase auth on every endpoint except user creation"
```

---

## Task 4: Documentation

**Files:**
- Modify: `OpenPoints.md`

**Interfaces:**
- Consumes: everything from Tasks 1-3.
- Produces: nothing (terminal task).

- [ ] **Step 1: Replace the "Auth & authorization" section**

Change:
```markdown
## Auth & authorization
- No authentication or authorization exists on any endpoint. Anyone can
  create/update any user, group, or task, or assign tasks to arbitrary
  users. Needs a decision on auth scheme (session, JWT, API key) before
  this is exposed beyond local development.
```
to:
```markdown
## Auth & authorization
- Authentication (not authorization) now exists on every endpoint except
  `POST /api/v1/users` (user creation, which must remain callable
  pre-signup). Callers must send `Authorization: Bearer <Firebase_ID_Token>`;
  `app.auth.verify_firebase_token` (a FastAPI dependency wired in at the
  router level for `groups.py`, `user_group.py`, `tasks.py`,
  `task_group.py`, and per-route for the 3 non-create routes in
  `users.py`) validates the token via `firebase_admin.auth.verify_id_token`
  and rejects missing/malformed/invalid/expired tokens with HTTP 401.
- This is authentication only — it proves a valid Firebase-issued token
  was presented, nothing more. There is still NO authorization/ownership
  enforcement anywhere: any authenticated Firebase user can read or
  mutate any User, Group, or Task regardless of who created it. The
  Firebase `uid` extracted from the token is returned by
  `verify_firebase_token` but not currently checked against resource
  ownership (e.g. `Group.groupCreaterId`, `Task.createdBy`) in any service.
- The Firebase `uid` has NO mapping to this app's own `User.userId`.
  These are two different, unrelated ID spaces: `User.userId` is a
  server-generated UUID4 created by `UserService.create_user` with no
  link back to Firebase identity. A future iteration would need an
  explicit `User.firebaseUid` column (or equivalent lookup) plus
  per-route ownership checks before this becomes real authorization.
- Local prerequisite: `app/firebase/firebase-adminsdk.json` (a Firebase
  service-account credential, gitignored via `app/firebase/` in
  `.gitignore` and never committed) must be present on disk before the
  app can start — `app/auth.py` reads it at import time. The path is
  overridable via the `FIREBASE_CREDENTIALS_PATH` env var.
```

- [ ] **Step 2: Add a Deployment bullet about the credential**

In the `## Deployment` section, after the existing Docker bullet, add:
```markdown
- The Firebase service-account credential (`app/firebase/firebase-adminsdk.json`)
  is required at container start but is gitignored, so a plain
  `docker build` from a clean checkout will NOT have it. Needs an explicit
  decision: bake a build-time secret (Docker BuildKit `--secret`), mount it
  as a runtime volume, or inject the JSON contents via an env var and have
  `app/auth.py` support loading credentials from an env-var string in
  addition to a file path. Not resolved by this change.
```

- [ ] **Step 3: Run the full suite once more**

Run: `.venv/bin/pytest -v`
Expected: PASS — documentation-only change, confirms nothing regressed.

- [ ] **Step 4: Commit**

```bash
git add OpenPoints.md
git commit -m "docs: describe the new Firebase authentication and its known gaps"
```

---

## Self-Review

**Spec coverage:** `ASK.md`'s "integrate firebase admin sdk" + credential path → Task 2. "Build a utility/function to validate the token" → `app/auth.py`'s `verify_firebase_token`, Task 2. "Function should be added for all API routes (except Create a user)" → Task 3's per-router/per-route wiring. "Extract the userId from this token" → `verify_firebase_token`'s return value (the Firebase `uid`). "Update OpenPoints.md after task execution" → Task 4. The security gap found during planning (ungitignored credential) → Task 1, sequenced first.

**Placeholder scan:** every step has literal code, an exact diff, or an exact command with expected output.

**Type consistency:** `verify_firebase_token`'s signature (`authorization: str | None = Header(None)) -> str`) is identical everywhere it's defined (Task 2) and referenced (Task 3's router wiring and `tests/conftest.py`'s override). The `unauthenticated_client` fixture's repository/service construction exactly mirrors `client`'s existing block, just omitting the one auth override line.
