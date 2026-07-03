# TaskNest Error-Handling Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the two issues in `requirements.md` — (1) `BadRequestError`'s HTTP response `detail` is currently an inline dict literal duplicated across three routers; replace it with a single reusable Pydantic entity, and (2) no route documents the error responses it can actually return; add `responses={}` metadata to every route's decorator for each status code it can raise.

**Architecture:** No new layers or behavior changes — this is a documentation/DRY cleanup on top of the existing `NotFoundError` → 404 / `BadRequestError` → 400 mapping already in place in all five routers. A new `app/schemas/errors.py` defines the reusable entity; routers import it in place of the inline dict and add `responses=` to their `@router.*` decorators.

**Tech Stack:** Same as the existing project — FastAPI, Pydantic v2, pytest. No new dependencies.

**Execution:** Approved for subagent-driven execution (superpowers:subagent-driven-development) — one implementer subagent per task, with a task reviewer between tasks.

## Global Constraints

- Only `BadRequestError`'s `detail` gets a structured entity. `NotFoundError`'s `detail` stays a plain string (`detail=str(exc)`) — explicitly confirmed, not part of this fix.
- `responses={}` metadata must be added for **every** status code a route can actually raise (404 wherever `NotFoundError` is caught, 400 wherever `BadRequestError` is caught) — confirmed explicitly, covering all five routers.
- Keep the existing per-router `try/except NotFoundError` / `except BadRequestError` blocks exactly as they are — do **not** consolidate them into a global FastAPI exception handler. This was an explicit choice: smallest, most targeted fix matching what `requirements.md` describes as broken.
- The response body's actual JSON shape must not change for existing consumers/tests: `{"detail": {"errorCode": "...", "message": "..."}}` for 400s, `{"detail": "<string>"}` for 404s. Swapping the dict literal for a Pydantic model's `.model_dump()` output must produce byte-for-byte the same dict.
- Follow existing conventions: no docstrings/comments in `app/`, one schema file per domain concept under `app/schemas/`.

---

## Context

`requirements.md` was updated (by the user) to describe two follow-up code-quality fixes on top of the already-shipped TaskNest API and its `BadRequestError`/`ErrorCode` mechanism (added in the prior validation-gap-fixes work, commits `d6519cb`/`60b0cd6`/`b773e91`): (1) the `detail={"errorCode": exc.error_code, "message": exc.message}` dict is written out as an inline literal in three separate routers (`app/api/v1/tasks.py`, `app/api/v1/task_group.py`, `app/api/v1/user_group.py`) instead of being a single reusable type, and (2) none of the five routers declare their possible error responses via FastAPI's `responses=` decorator parameter, so the auto-generated OpenAPI docs don't show that e.g. `GET /api/v1/groups/{group_id}` can 404. Clarified during planning: introduce the reusable entity for `BadRequestError` only (not `NotFoundError`), keep the existing per-router `try/except` structure exactly as-is (no global exception handler), and add `responses=` entries for every 404 and 400 a route can actually produce, across all five routers.

---

## File Structure

```
app/schemas/errors.py                    # NEW — ErrorDetail, BadRequestResponse Pydantic models
app/api/v1/users.py                      # + responses= on 3 routes (404 only)
app/api/v1/groups.py                     # + responses= on 4 routes (404 only)
app/api/v1/user_group.py                 # detail= now uses ErrorDetail; + responses= on both routes
app/api/v1/tasks.py                      # detail= now uses ErrorDetail; + responses= on 4 routes
app/api/v1/task_group.py                 # detail= now uses ErrorDetail; + responses= on both routes
```

No test files need new test cases — this changes response *documentation* and the *construction* of an already-existing dict, not its resulting JSON shape or any status code. Existing tests (e.g. `tests/integration/test_task_group_api.py::test_assign_task_to_non_member_returns_400`, which already asserts `response.json()["detail"]["errorCode"] == "ERR_TASKS_001"`) serve as the regression check that the dict shape is unchanged.

---

## Task 1: Reusable `BadRequestError` detail entity

**Files:**
- Create: `app/schemas/errors.py`
- Modify: `app/api/v1/tasks.py` (only the `update_task_state` `except BadRequestError` block)
- Modify: `app/api/v1/task_group.py` (only the `assign_task` `except BadRequestError` block)
- Modify: `app/api/v1/user_group.py` (only the `associate_user` `except BadRequestError` block)

**Interfaces:**
- Consumes: `BadRequestError` (`.error_code`, `.message`, `.http_code`) from `app/exceptions.py` (unchanged).
- Produces: `ErrorDetail(errorCode: str, message: str)` and `BadRequestResponse(detail: ErrorDetail)` (both Pydantic `BaseModel`) in `app/schemas/errors.py` — `ErrorDetail` is consumed by all three routers in this task (for the actual `detail=` value) and by Task 2 (as the `"model"` in `responses={400: ...}` via the `BadRequestResponse` wrapper, since the real response body nests it under `"detail"`).

- [ ] **Step 1: Write `app/schemas/errors.py`**

```python
from pydantic import BaseModel


class ErrorDetail(BaseModel):
    errorCode: str
    message: str


class BadRequestResponse(BaseModel):
    detail: ErrorDetail
```

- [ ] **Step 2: Update `app/api/v1/tasks.py`'s `BadRequestError` handling**

Add the import and replace the inline dict:

```python
from app.schemas.errors import ErrorDetail
```

```python
    except BadRequestError as exc:
        raise HTTPException(
            status_code=exc.http_code,
            detail=ErrorDetail(errorCode=exc.error_code, message=exc.message).model_dump(),
        ) from exc
```

(This is the only change to this file in this task — the `except NotFoundError` blocks and everything else stay untouched.)

- [ ] **Step 3: Update `app/api/v1/task_group.py`'s `BadRequestError` handling**

Same pattern — add the import and replace the inline dict in `assign_task`:

```python
from app.schemas.errors import ErrorDetail
```

```python
    except BadRequestError as exc:
        raise HTTPException(
            status_code=exc.http_code,
            detail=ErrorDetail(errorCode=exc.error_code, message=exc.message).model_dump(),
        ) from exc
```

- [ ] **Step 4: Update `app/api/v1/user_group.py`'s `BadRequestError` handling**

Same pattern — add the import and replace the inline dict in `associate_user`:

```python
from app.schemas.errors import ErrorDetail
```

```python
    except BadRequestError as exc:
        raise HTTPException(
            status_code=exc.http_code,
            detail=ErrorDetail(errorCode=exc.error_code, message=exc.message).model_dump(),
        ) from exc
```

- [ ] **Step 5: Run the full test suite to confirm no regression**

Run: `pytest -v`
Expected: all 62 tests still pass — in particular, confirm these three (which assert the exact `errorCode` in the response body) still pass unchanged:
- `tests/integration/test_task_group_api.py::test_assign_task_to_non_member_returns_400`
- `tests/integration/test_tasks_api.py::test_update_task_state_already_completed_returns_400`
- `tests/integration/test_user_group_api.py::test_associate_duplicate_returns_400`

- [ ] **Step 6: Commit**

```bash
git add app/schemas/errors.py app/api/v1/tasks.py app/api/v1/task_group.py app/api/v1/user_group.py
git commit -m "refactor: introduce reusable ErrorDetail entity for BadRequestError responses"
```

---

## Task 2: Document error responses on every route

**Files:**
- Modify: `app/api/v1/users.py`
- Modify: `app/api/v1/groups.py`
- Modify: `app/api/v1/user_group.py`
- Modify: `app/api/v1/tasks.py`
- Modify: `app/api/v1/task_group.py`

**Interfaces:**
- Consumes: `BadRequestResponse` from `app/schemas/errors.py` (Task 1) — used as the `"model"` for every `responses={400: ...}` entry added in this task.

This task only adds a `responses={...}` keyword argument to existing `@router.*(...)` decorators — no other line in any of these files changes. Below is the exact `responses=` value for every route that can raise an error; routes not listed (`create_user`, `get_groups_by_creator`) raise nothing and are left untouched.

- [ ] **Step 1: `app/api/v1/users.py` — add `responses=` to the three 404-capable routes**

```python
@router.get(
    "/{user_id}",
    response_model=UserResponse,
    responses={404: {"description": "User not found"}},
)
def get_user(user_id: str, service: UserService = Depends(get_user_service)) -> UserResponse:
```

```python
@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    responses={404: {"description": "User not found"}},
)
def update_user(
    user_id: str, payload: UserUpdateRequest, service: UserService = Depends(get_user_service)
) -> UserResponse:
```

```python
@router.patch(
    "/{user_id}/status",
    response_model=UserResponse,
    responses={404: {"description": "User not found"}},
)
def update_user_status(
    user_id: str,
    payload: UserStatusUpdateRequest,
    service: UserService = Depends(get_user_service),
) -> UserResponse:
```

(`create_user`'s decorator is unchanged — it never raises.)

- [ ] **Step 2: `app/api/v1/groups.py` — add `responses=` to the four 404-capable routes**

```python
@router.post(
    "/groups",
    response_model=GroupResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"description": "Group creator (user) not found"}},
)
def create_group(
    payload: GroupCreateRequest, service: GroupService = Depends(get_group_service)
) -> GroupResponse:
```

```python
@router.get(
    "/groups/{group_id}",
    response_model=GroupResponse,
    responses={404: {"description": "Group not found"}},
)
def get_group(group_id: str, service: GroupService = Depends(get_group_service)) -> GroupResponse:
```

```python
@router.patch(
    "/groups/{group_id}",
    response_model=GroupResponse,
    responses={404: {"description": "Group not found"}},
)
def update_group(
    group_id: str, payload: GroupUpdateRequest, service: GroupService = Depends(get_group_service)
) -> GroupResponse:
```

```python
@router.patch(
    "/groups/{group_id}/status",
    response_model=GroupResponse,
    responses={404: {"description": "Group not found"}},
)
def update_group_status(
    group_id: str,
    payload: GroupStatusUpdateRequest,
    service: GroupService = Depends(get_group_service),
) -> GroupResponse:
```

(`get_groups_by_creator`'s decorator is unchanged — it never raises.)

- [ ] **Step 3: `app/api/v1/user_group.py` — add `responses=` to both routes**

Add the import for `BadRequestResponse` alongside the existing `ErrorDetail` import from Task 1:

```python
from app.schemas.errors import BadRequestResponse, ErrorDetail
```

```python
@router.post(
    "/{group_id}/members",
    response_model=UserGroupResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"description": "User or Group not found"},
        400: {"model": BadRequestResponse, "description": "User is already associated with this group"},
    },
)
def associate_user(
    group_id: str,
    payload: UserGroupAssociateRequest,
    service: UserGroupService = Depends(get_user_group_service),
) -> UserGroupResponse:
```

```python
@router.delete(
    "/{group_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"description": "User is not associated with this group"}},
)
def disassociate_user(
    group_id: str, user_id: str, service: UserGroupService = Depends(get_user_group_service)
) -> None:
```

- [ ] **Step 4: `app/api/v1/tasks.py` — add `responses=` to all five error-capable routes**

Add the import:

```python
from app.schemas.errors import BadRequestResponse, ErrorDetail
```

`create_task` raises `NotFoundError` if `createdBy` doesn't exist:

```python
@router.post(
    "",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"description": "Task creator (user) not found"}},
)
def create_task(
    payload: TaskCreateRequest, service: TaskService = Depends(get_task_service)
) -> TaskResponse:
```

```python
@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    responses={404: {"description": "Task not found"}},
)
def get_task(task_id: str, service: TaskService = Depends(get_task_service)) -> TaskResponse:
```

```python
@router.patch(
    "/{task_id}",
    response_model=TaskResponse,
    responses={404: {"description": "Task or updating user not found"}},
)
def update_task_meta(
    task_id: str, payload: TaskMetaUpdateRequest, service: TaskService = Depends(get_task_service)
) -> TaskResponse:
```

```python
@router.patch(
    "/{task_id}/state",
    response_model=TaskResponse,
    responses={
        404: {"description": "Task or updating user not found"},
        400: {
            "model": BadRequestResponse,
            "description": "Task is already COMPLETED and cannot be marked COMPLETED again",
        },
    },
)
def update_task_state(
    task_id: str, payload: TaskStateUpdateRequest, service: TaskService = Depends(get_task_service)
) -> TaskResponse:
```

```python
@router.patch(
    "/{task_id}/due-date",
    response_model=TaskResponse,
    responses={404: {"description": "Task or updating user not found"}},
)
def update_due_date(
    task_id: str, payload: TaskDueDateUpdateRequest, service: TaskService = Depends(get_task_service)
) -> TaskResponse:
```

- [ ] **Step 5: `app/api/v1/task_group.py` — add `responses=` to both routes**

Add the import:

```python
from app.schemas.errors import BadRequestResponse, ErrorDetail
```

```python
@router.post(
    "",
    response_model=TaskGroupResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"description": "Task, Group, or Assignee (user) not found"},
        400: {
            "model": BadRequestResponse,
            "description": "Assignee is not a member of the target group",
        },
    },
)
def assign_task(
    group_id: str,
    task_id: str,
    payload: TaskGroupAssignRequest,
    service: TaskGroupService = Depends(get_task_group_service),
) -> TaskGroupResponse:
```

```python
@router.delete(
    "/{assignee_id}",
    response_model=TaskGroupResponse,
    responses={404: {"description": "No matching task-group assignment found for that assignee"}},
)
def unassign_task(
    group_id: str,
    task_id: str,
    assignee_id: str,
    service: TaskGroupService = Depends(get_task_group_service),
) -> TaskGroupResponse:
```

- [ ] **Step 6: Run the full test suite**

Run: `pytest -v`
Expected: all 62 tests pass unchanged — `responses=` is documentation-only metadata for FastAPI's OpenAPI schema generation and has no effect on runtime request handling.

- [ ] **Step 7: Verify the OpenAPI schema picked up the new responses**

Run:
```bash
source .venv/bin/activate
uvicorn app.main:app --port 8124 &
sleep 1
curl -s localhost:8124/openapi.json | python3 -c "
import json, sys
spec = json.load(sys.stdin)
get_group = spec['paths']['/api/v1/groups/{group_id}']['get']['responses']
assign = spec['paths']['/api/v1/groups/{group_id}/tasks/{task_id}/assignee']['post']['responses']
assert '404' in get_group, get_group
assert '404' in assign and '400' in assign, assign
print('get /groups/{group_id} responses:', list(get_group.keys()))
print('post assignee responses:', list(assign.keys()))
print('OK')
"
kill %1
```
Expected: `OK` printed, with `404` present for the group-fetch route and both `400`/`404` present for the assign route (alongside FastAPI's always-present `200`/`422`).

- [ ] **Step 8: Commit**

```bash
git add app/api/v1/users.py app/api/v1/groups.py app/api/v1/user_group.py \
        app/api/v1/tasks.py app/api/v1/task_group.py
git commit -m "docs: declare error responses on all routes for OpenAPI docs"
```

---

## Verification (end-to-end)

1. `pytest -v` — full suite green, 62/62, 0 failures.
2. `curl localhost:PORT/openapi.json` (server running) — spot-check that routes which raise `NotFoundError` show a `404` entry and routes which also raise `BadRequestError` show a `400` entry with `BadRequestResponse`'s schema (nesting `ErrorDetail` under `detail`).
3. Manually re-run the three `curl` checks from the previous session (assign to non-member, re-complete a COMPLETED task, duplicate associate) and confirm the JSON body shape (`{"detail": {"errorCode": ..., "message": ...}}`) is byte-for-byte identical to before this change.
