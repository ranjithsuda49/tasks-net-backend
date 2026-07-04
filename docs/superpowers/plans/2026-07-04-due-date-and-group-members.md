# Nullable Due Date & Group Members Endpoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the two open items ASK.md calls out from `OpenPoints.md`: (1) let `PATCH /api/v1/tasks/{task_id}/due-date` accept `null` to clear a task's due date, and (2) add `GET /api/v1/groups/{group_id}/members` to read a group's members, 404ing on an unknown group.

**Architecture:** Both changes stay within the existing layered structure (`app/api/v1` → `app/services` → `app/repositories`). Change 1 widens an existing Pydantic schema field and a service parameter type — no new logic, since the domain model and the service's `model_copy` overwrite already support `None`. Change 2 adds an existence check to an already-existing but unused service method (`UserGroupService.list_by_group`) and exposes it via a new router endpoint on the existing `user_group` router.

**Tech Stack:** FastAPI, Pydantic v2, pytest + `fastapi.testclient.TestClient`, in-memory repositories (no DB).

## Global Constraints

- Follow the codebase's existing conventions exactly: routers only translate `NotFoundError`/`BadRequestError` to `HTTPException`, never contain business logic; services raise domain exceptions rather than returning error codes/None-as-error; list endpoints return a bare `list[XResponse]` with no envelope object (see `GET /api/v1/users/{user_id}/groups` in `app/api/v1/groups.py` for the precedent).
- No lint/format tooling is configured in this repo — don't add any.
- Run tests with the project's venv: `.venv/bin/pytest` (or activate `.venv` first).

---

## Task 1: Nullable task due date

**Files:**
- Modify: `app/schemas/task.py:27-29` (`TaskDueDateUpdateRequest`)
- Modify: `app/services/task_service.py:78` (`TaskService.update_due_date` signature only)
- Test: `tests/integration/test_tasks_api.py` (new test)
- Test: `tests/unit/test_task_service.py` (new test)

**Interfaces:**
- Consumes: existing `TaskService.update_due_date(self, task_id: str, updated_by: str, due_date: datetime) -> Task` (defined at `app/services/task_service.py:78-88`); existing `PATCH /api/v1/tasks/{task_id}/due-date` route in `app/api/v1/tasks.py:103-115` (unchanged — it passes `payload.taskDueDate` straight through).
- Produces: `TaskDueDateUpdateRequest.taskDueDate` becomes `Optional[datetime] = None`; `TaskService.update_due_date`'s `due_date` parameter becomes `Optional[datetime]`. No other task consumes these beyond what's listed above.

- [ ] **Step 1: Write the failing integration test**

Add to the end of `tests/integration/test_tasks_api.py`:

```python
def test_update_task_due_date_to_null_clears_it(client):
    user_id = _create_user(client)
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": user_id}
    ).json()["taskId"]
    client.patch(
        f"/api/v1/tasks/{task_id}/due-date",
        json={"updatedBy": user_id, "taskDueDate": "2026-08-01T00:00:00Z"},
    )

    response = client.patch(
        f"/api/v1/tasks/{task_id}/due-date",
        json={"updatedBy": user_id, "taskDueDate": None},
    )
    assert response.status_code == 200
    assert response.json()["taskDueDate"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/integration/test_tasks_api.py::test_update_task_due_date_to_null_clears_it -v`
Expected: FAIL with status code `422` (Pydantic rejects `null` for the currently-required `datetime` field `taskDueDate`), not `200`.

- [ ] **Step 3: Widen the schema field**

In `app/schemas/task.py`, change:

```python
class TaskDueDateUpdateRequest(BaseModel):
    updatedBy: str
    taskDueDate: datetime
```

to:

```python
class TaskDueDateUpdateRequest(BaseModel):
    updatedBy: str
    taskDueDate: Optional[datetime] = None
```

- [ ] **Step 4: Widen the service parameter type**

In `app/services/task_service.py`, change line 78 from:

```python
    def update_due_date(self, task_id: str, updated_by: str, due_date: datetime) -> Task:
```

to:

```python
    def update_due_date(self, task_id: str, updated_by: str, due_date: Optional[datetime]) -> Task:
```

The method body (lines 79-88) needs no change — `model_copy(update={"taskDueDate": due_date, ...})` already unconditionally overwrites, so `None` correctly clears the field.

- [ ] **Step 5: Run the integration test to verify it passes**

Run: `.venv/bin/pytest tests/integration/test_tasks_api.py::test_update_task_due_date_to_null_clears_it -v`
Expected: PASS

- [ ] **Step 6: Add a unit test for the same guarantee at the service layer**

Add to `tests/unit/test_task_service.py`, after `test_update_due_date` (after line 93):

```python
def test_update_due_date_clears_existing_due_date(task_service: TaskService, user_service: UserService):
    user = user_service.create_user(first_name="Ada", last_name="Lovelace")
    task = task_service.create_task(task_title="Buy milk", created_by=user.userId)
    existing_due_date = datetime.now(timezone.utc) + timedelta(days=3)
    task_service.update_due_date(task.taskId, updated_by=user.userId, due_date=existing_due_date)

    cleared = task_service.update_due_date(task.taskId, updated_by=user.userId, due_date=None)

    assert cleared.taskDueDate is None
    assert cleared.updatedBy == user.userId
    assert cleared.updatedAt is not None
```

- [ ] **Step 7: Run the full affected test files**

Run: `.venv/bin/pytest tests/unit/test_task_service.py tests/integration/test_tasks_api.py -v`
Expected: PASS — all tests in both files, including the pre-existing `test_update_due_date` and `test_update_task_due_date` (unaffected by the widening since they still pass concrete datetimes).

- [ ] **Step 8: Commit**

```bash
git add app/schemas/task.py app/services/task_service.py tests/unit/test_task_service.py tests/integration/test_tasks_api.py
git commit -m "feat: allow clearing a task's due date via null"
```

---

## Task 2: `GET /api/v1/groups/{group_id}/members`

**Files:**
- Modify: `app/services/user_group_service.py:37-38` (`UserGroupService.list_by_group`)
- Modify: `app/api/v1/user_group.py` (add new route)
- Test: `tests/unit/test_user_group_service.py` (new tests)
- Test: `tests/integration/test_user_group_api.py` (new tests)

**Interfaces:**
- Consumes: `GroupService.get_group(group_id: str) -> Group` (raises `NotFoundError` if missing — already used by `UserGroupService.associate` at `app/services/user_group_service.py:23`); `InMemoryUserGroupRepository.list_by_group(group_id: str) -> list[UserGroupRelationship]` (already exists, `app/repositories/user_group_repository.py:36-37`); `UserGroupResponse` schema (already exists, `app/schemas/user_group.py:9-13`, mirrors `UserGroupRelationship` field-for-field).
- Produces: `UserGroupService.list_by_group(self, group_id: str) -> list[UserGroupRelationship]` now raises `NotFoundError` for an unknown group (previously silently returned `[]`); new route `GET /api/v1/groups/{group_id}/members` returning `list[UserGroupResponse]`, 404 on missing group.

- [ ] **Step 1: Write the failing unit tests**

Add to `tests/unit/test_user_group_service.py`, after `test_disassociate_removes_relationship` (after line 71):

```python
def test_list_by_group_returns_members(user_group_service: UserGroupService, group_service, user_service):
    user, group = _make_user_and_group(user_service, group_service)
    user_group_service.associate(user.userId, group.groupId, "Father")

    members = user_group_service.list_by_group(group.groupId)

    assert len(members) == 1
    assert members[0].userId == user.userId
    assert members[0].groupId == group.groupId
    assert members[0].relationship == "Father"


def test_list_by_group_raises_if_group_missing(user_group_service: UserGroupService):
    with pytest.raises(NotFoundError):
        user_group_service.list_by_group("unknown-group")
```

- [ ] **Step 2: Run tests to verify the missing-group test fails**

Run: `.venv/bin/pytest tests/unit/test_user_group_service.py::test_list_by_group_raises_if_group_missing -v`
Expected: FAIL — no exception is raised today; `list_by_group` currently returns `[]` for any unknown group id instead of raising `NotFoundError`.

(`test_list_by_group_returns_members` will already pass at this point since the repository-level filtering already works — that's expected and fine; it's a regression-coverage test, not a TDD-driving one.)

- [ ] **Step 3: Add the existence check to the service**

In `app/services/user_group_service.py`, change lines 37-38 from:

```python
    def list_by_group(self, group_id: str) -> list[UserGroupRelationship]:
        return self._repository.list_by_group(group_id)
```

to:

```python
    def list_by_group(self, group_id: str) -> list[UserGroupRelationship]:
        self._group_service.get_group(group_id)
        return self._repository.list_by_group(group_id)
```

- [ ] **Step 4: Run the unit tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_user_group_service.py -v`
Expected: PASS — all tests in the file, including the pre-existing `test_disassociate_removes_relationship` (it calls `list_by_group` on a group it created earlier in the same test, so the new existence check doesn't affect it).

- [ ] **Step 5: Write the failing integration tests**

Add to the end of `tests/integration/test_user_group_api.py`:

```python
def test_get_group_members_returns_associated_users(client):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)
    client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": creator_id, "relationship": "Father"}
    )

    response = client.get(f"/api/v1/groups/{group_id}/members")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["userId"] == creator_id
    assert body[0]["groupId"] == group_id
    assert body[0]["relationship"] == "Father"


def test_get_group_members_empty_list_for_group_with_no_members(client):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)

    response = client.get(f"/api/v1/groups/{group_id}/members")
    assert response.status_code == 200
    assert response.json() == []


def test_get_group_members_unknown_group_returns_404(client):
    response = client.get("/api/v1/groups/unknown-group/members")
    assert response.status_code == 404
```

- [ ] **Step 6: Run tests to verify the 200-expecting tests fail**

Run: `.venv/bin/pytest tests/integration/test_user_group_api.py -v`
Expected: `test_get_group_members_returns_associated_users` and `test_get_group_members_empty_list_for_group_with_no_members` FAIL with `404` (no such route exists yet, so FastAPI itself 404s). `test_get_group_members_unknown_group_returns_404` will already PASS — coincidentally, since a missing route and a missing group both 404 today; it becomes a meaningful assertion only once the route exists in Step 7.

- [ ] **Step 7: Add the router endpoint**

In `app/api/v1/user_group.py`, add this route between the existing `POST "/{group_id}/members"` and `DELETE "/{group_id}/members/{user_id}"` routes (no new imports needed — `NotFoundError`, `UserGroupResponse`, `UserGroupService`, `get_user_group_service` are already imported in this file):

```python
@router.get(
    "/{group_id}/members",
    response_model=list[UserGroupResponse],
    responses={404: {"description": "Group not found"}},
)
def get_group_members(
    group_id: str, service: UserGroupService = Depends(get_user_group_service)
) -> list[UserGroupResponse]:
    try:
        relationships = service.list_by_group(group_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [UserGroupResponse(**r.model_dump()) for r in relationships]
```

- [ ] **Step 8: Run tests to verify they all pass**

Run: `.venv/bin/pytest tests/integration/test_user_group_api.py -v`
Expected: PASS — all tests in the file.

- [ ] **Step 9: Run the full suite to check for regressions**

Run: `.venv/bin/pytest -v`
Expected: PASS — every test in the project, in particular anything else touching `UserGroupService` (e.g. `tests/unit/test_task_group_service.py`, `tests/integration/test_task_group_api.py`, since `TaskGroupService` composes `UserGroupService`).

- [ ] **Step 10: Commit**

```bash
git add app/services/user_group_service.py app/api/v1/user_group.py tests/unit/test_user_group_service.py tests/integration/test_user_group_api.py
git commit -m "feat: add GET endpoint to fetch a group's members"
```

---

## Task 3: Documentation cleanup

**Files:**
- Modify: `OpenPoints.md`
- Modify: `CLAUDE.md`
- Modify: `Arch.md`

**Interfaces:**
- Consumes: nothing from Tasks 1-2 beyond the fact that both fixes now exist and are tested.
- Produces: nothing consumed by later tasks — this is the terminal task.

- [ ] **Step 1: Remove the resolved due-date bullet from `OpenPoints.md` and promote the Error codes subsection**

In `OpenPoints.md`, change:

```markdown
## Validation gaps
- `PATCH /api/v1/tasks/{task_id}/due-date` requires a `taskDueDate` value
  (`TaskDueDateUpdateRequest.taskDueDate: datetime`, not `Optional`), so
  there is currently no way to clear a task's due date back to `null` via
  the API — even though `Task.taskDueDate` on the domain model itself is
  `Optional[datetime]`.

### Error codes
```

to:

```markdown
## Error codes
```

(This removes the now-resolved bullet and its now-empty parent heading, promoting the "Error codes" content — which describes a mechanism, not a gap — to its own top-level section.)

- [ ] **Step 2: Narrow the group-members bullet in `OpenPoints.md`**

In `OpenPoints.md`, under `## API surface gaps`, change:

```markdown
- No GET endpoint to read a group's members or a user's memberships — only
  `POST`/`DELETE` exist for `User`-`Group` associations. As a result,
  `InMemoryUserGroupRepository.list_by_group` is currently dead code in
  production (only exercised by tests, via `UserGroupService.list_by_group`).
  This matches the original spec, which only asked for associate/
  de-associate, so it's not a bug — just a gap for a future task.
```

to:

```markdown
- No GET endpoint to read a user's memberships (i.e. "all groups a given
  user belongs to") — only the group → members direction exists
  (`GET /api/v1/groups/{groupId}/members`).
```

- [ ] **Step 3: Remove the stale due-date bullet from `CLAUDE.md`**

In `CLAUDE.md`, under "Things that aren't obvious from one file", remove:

```markdown
- `PATCH /api/v1/tasks/{task_id}/due-date` requires `taskDueDate` — there is
  currently no way to clear a task's due date back to `null` via the API.
```

- [ ] **Step 4: Add the new route to `Arch.md`'s endpoint inventory**

In `Arch.md`, in the API Endpoint Inventory table, change:

```markdown
| POST | /api/v1/groups/{groupId}/members | Associate a user to a group |
| DELETE | /api/v1/groups/{groupId}/members/{userId} | De-associate a user from a group |
```

to:

```markdown
| POST | /api/v1/groups/{groupId}/members | Associate a user to a group |
| GET | /api/v1/groups/{groupId}/members | Fetch a group's members |
| DELETE | /api/v1/groups/{groupId}/members/{userId} | De-associate a user from a group |
```

- [ ] **Step 5: Run the full suite once more**

Run: `.venv/bin/pytest -v`
Expected: PASS — documentation-only changes, no code touched in this task, but confirms nothing upstream broke.

- [ ] **Step 6: Commit**

```bash
git add OpenPoints.md CLAUDE.md Arch.md
git commit -m "docs: remove resolved due-date and group-members gaps from OpenPoints.md"
```

---

## Self-Review Notes

- **Spec coverage:** ASK.md's two asks (nullable due date; GET group members with 404 handling) are each covered by Task 1 / Task 2, including the explicit "update test cases" and "remove the item from OpenPoints.md" instructions (Task 3).
- **Type consistency:** `TaskDueDateUpdateRequest.taskDueDate`, `TaskService.update_due_date`'s `due_date` param, and `Task.taskDueDate` are all `Optional[datetime]` after Task 1 — consistent end-to-end. `UserGroupService.list_by_group` signature is unchanged (`(self, group_id: str) -> list[UserGroupRelationship]`); only its raising behavior changes, and every call site (the new router, the two new unit tests, the one pre-existing unit test) is accounted for.
- **No placeholders:** every step above has literal code to write or an exact command with its expected result.
