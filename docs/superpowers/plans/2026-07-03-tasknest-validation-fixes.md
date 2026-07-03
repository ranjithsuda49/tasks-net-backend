# TaskNest Validation Gap Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close three documented validation gaps in TaskNest's `OpenPoints.md` — (a) task assignment doesn't verify group membership, (b) task state transitions are fully unrestricted, (c) a user can be added to the same group twice — and introduce a shared `BadRequestError`/error-code mechanism in `app/exceptions.py` so the service layer can raise structured, client-facing 400 errors.

**Architecture:** No new layers. Each fix lives entirely inside its existing service method (`TaskGroupService.assign`, `TaskService.update_task_state`, `UserGroupService.associate`), raising the new `BadRequestError` from `app/exceptions.py`. Each router already has a `try/except NotFoundError` block around its call into the service — add a sibling `except BadRequestError` clause that maps to `HTTPException(400, ...)` with the error code and message in the body, following the exact same pattern already used for `NotFoundError` → 404 across all five routers.

**Tech Stack:** Same as the existing project — FastAPI, Pydantic v2, pytest, httpx `TestClient`. No new dependencies.

## Global Constraints

- All three new validation failures return **HTTP 400**, not 404 or 409 — this was explicit in the request even though a duplicate-membership conflict might otherwise suggest 409.
- Error codes follow the format `ERR_TASKS_XXX` (sequential, numeric, zero-padded to 3 digits) regardless of which entity the error is about — this was an explicit, deliberate choice by the user, not a mistake to "fix" toward per-entity prefixes.
- Rule (b) is narrower than a literal reading of "if task is done as COMPLETED, throw 400": it only blocks moving `COMPLETED` → `COMPLETED` again. Moving `COMPLETED` → `TODO` or `COMPLETED` → `IN-PROGRESS` remains allowed — this was an explicit clarification from the user, not the more restrictive "COMPLETED is fully terminal" reading.
- `BadRequestError` carries `http_code` (int, always 400 here), `error_code` (one of the new `ErrorCode` constants), and `message` (short human-readable text, defaulted from a lookup table keyed by `error_code` so the message only has to be written once).
- Existing tests that currently assign a task to a user who was never explicitly added to the group (e.g. using the group creator directly as assignee, with no prior `POST .../members` call) must be updated to associate that user first — approved explicitly by the user. Do not leave them broken.
- Follow existing code conventions exactly: no docstrings/comments anywhere in this codebase's `app/` tree (verified — none exist), constructor-injected dependencies typed against the narrowest existing pattern (concrete `InMemory*Repository` where the codebase already does this, `BaseRepository[T]` elsewhere), and the `except NotFoundError as exc: raise HTTPException(...) from exc` chaining style in every router.

---

## Context

TaskNest's `OpenPoints.md` documents three known validation gaps from the original build, all under "Validation gaps": (a) `TaskGroupService.assign` never checks that the assignee is actually a member of the group being assigned into (no cross-check against `UserGroupRelationship`), (b) `TaskService.update_task_state` allows any state transition including no-op re-completion, and (c) `UserGroupService.associate` allows the same user to be added to the same group multiple times, creating duplicate `UserGroupRelationship` rows. The user has now asked to close all three gaps, each raising HTTP 400 with a structured error code, and wants a reusable `BadRequestError` + `ErrorCode` mechanism added to `app/exceptions.py` (which currently only has `NotFoundError` and an unused `ConflictError`) rather than three one-off exception types. Clarified during planning: rule (b) only blocks re-completing an already-`COMPLETED` task (not all transitions out of `COMPLETED`); error codes are sequential (`ERR_TASKS_001`, `002`, `003`) rather than descriptive; and existing tests that relied on the old permissive behavior should be updated rather than preserved.

---

## File Structure

No new files except one new integration test file for the duplicate-membership case if not folded into the existing one (see Task 3 — it will be added to the existing `tests/integration/test_user_group_api.py`, no new file needed). All changes are modifications to existing files:

```
app/exceptions.py                              # + ErrorCode, ERROR_CODE_MESSAGES, BadRequestError
app/services/task_group_service.py             # assign() membership check
app/services/task_service.py                   # update_task_state() re-completion guard
app/services/user_group_service.py             # associate() duplicate-membership guard
app/api/v1/task_group.py                       # + except BadRequestError in assign_task
app/api/v1/tasks.py                            # + except BadRequestError in update_task_state
app/api/v1/user_group.py                       # + except BadRequestError in associate_user
app/dependencies.py                            # get_task_group_service() gains user_group_service arg
tests/conftest.py                              # client fixture wires user_group_service into TaskGroupService
tests/unit/test_task_group_service.py          # fixture + _setup updated, new BadRequestError test
tests/unit/test_task_service.py                # new BadRequestError test + allowed-transition test
tests/unit/test_user_group_service.py          # new BadRequestError test
tests/integration/test_task_group_api.py       # existing assign tests updated, new 400 test
tests/integration/test_tasks_api.py            # new 400 test + allowed-transition test
tests/integration/test_user_group_api.py       # new 400 test
OpenPoints.md                                  # Validation gaps section updated to reflect fixes
```

---

## Task 1: `BadRequestError`/`ErrorCode` infrastructure + Rule (a) — assignee must be a group member

**Files:**
- Modify: `app/exceptions.py`
- Modify: `app/services/task_group_service.py`
- Modify: `app/services/user_group_service.py` (add `is_member` helper, used by Task 1; no behavior change to `associate` yet — that's Task 3)
- Modify: `app/api/v1/task_group.py`
- Modify: `app/dependencies.py`
- Modify: `tests/conftest.py`
- Test: `tests/unit/test_task_group_service.py`
- Test: `tests/integration/test_task_group_api.py`
- Create: `docs/superpowers/plans/2026-07-03-tasknest-validation-fixes.md` (copy of this plan file, committed to the repo for record-keeping — same convention as `docs/superpowers/plans/2026-07-01-tasknest-api.md` from the original build)

**Interfaces:**
- Consumes: existing `TaskService.get_task`, `GroupService.get_group`, `UserService.get_user`, `UserGroupService` (now also injected into `TaskGroupService`).
- Produces: `ErrorCode` (class with string constants), `ERROR_CODE_MESSAGES` (`dict[str, str]`), `BadRequestError(error_code: str, message: str | None = None)` with `.http_code`, `.error_code`, `.message` — consumed by Tasks 2 and 3.
- Produces: `UserGroupService.is_member(user_id: str, group_id: str) -> bool` — consumed only by `TaskGroupService.assign` in this task.
- Produces: `TaskGroupService.__init__` now takes a fifth positional dependency, `user_group_service: UserGroupService` — this changes the constructor signature; every call site must be updated in this task (dependencies.py, conftest.py, test fixtures).

- [ ] **Step 1: Save this plan into the repo**

Copy the plan file into the repo's docs folder and commit it, following the same convention used for the original build's plan:

```bash
mkdir -p docs/superpowers/plans
cp /Users/sudar/.claude/plans/create-a-implementation-plan-piped-frost.md \
   docs/superpowers/plans/2026-07-03-tasknest-validation-fixes.md
git add docs/superpowers/plans/2026-07-03-tasknest-validation-fixes.md
git commit -m "docs: add validation-gap-fixes implementation plan"
```

- [ ] **Step 2: Write the failing unit tests for `BadRequestError` usage in `TaskGroupService`**

Rewrite `tests/unit/test_task_group_service.py` in full (fixtures now build a `user_group_service` and thread it into `task_group_service`; `_setup` now associates both `creator` and `assignee` to the group so existing positive-path tests keep passing under the new membership rule; a new test covers the 400 rejection):

```python
import pytest

from app.exceptions import BadRequestError, ErrorCode, NotFoundError
from app.repositories.group_repository import InMemoryGroupRepository
from app.repositories.task_group_repository import InMemoryTaskGroupRepository
from app.repositories.task_repository import InMemoryTaskRepository
from app.repositories.user_group_repository import InMemoryUserGroupRepository
from app.repositories.user_repository import InMemoryUserRepository
from app.services.group_service import GroupService
from app.services.task_group_service import TaskGroupService
from app.services.task_service import TaskService
from app.services.user_group_service import UserGroupService
from app.services.user_service import UserService


@pytest.fixture
def user_service() -> UserService:
    return UserService(InMemoryUserRepository())


@pytest.fixture
def group_service(user_service: UserService) -> GroupService:
    return GroupService(InMemoryGroupRepository(), user_service)


@pytest.fixture
def task_service(user_service: UserService) -> TaskService:
    return TaskService(InMemoryTaskRepository(), user_service)


@pytest.fixture
def user_group_service(user_service: UserService, group_service: GroupService) -> UserGroupService:
    return UserGroupService(InMemoryUserGroupRepository(), user_service, group_service)


@pytest.fixture
def task_group_service(
    task_service: TaskService,
    group_service: GroupService,
    user_service: UserService,
    user_group_service: UserGroupService,
) -> TaskGroupService:
    return TaskGroupService(
        InMemoryTaskGroupRepository(), task_service, group_service, user_service, user_group_service
    )


def _setup(user_service, group_service, task_service, user_group_service):
    creator = user_service.create_user(first_name="Ada", last_name="Lovelace")
    assignee = user_service.create_user(first_name="Bob", last_name="Smith")
    group = group_service.create_group(
        group_name="Smiths", group_desc=None, group_category="Family", creater_id=creator.userId
    )
    task = task_service.create_task(task_title="Buy milk", created_by=creator.userId)
    user_group_service.associate(creator.userId, group.groupId, "Creator")
    user_group_service.associate(assignee.userId, group.groupId, "Member")
    return creator, assignee, group, task


def test_assign_raises_if_task_missing(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    _, assignee, group, _ = _setup(user_service, group_service, task_service, user_group_service)
    with pytest.raises(NotFoundError):
        task_group_service.assign("unknown-task", group.groupId, assignee.userId)


def test_assign_raises_if_group_missing(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    _, assignee, _, task = _setup(user_service, group_service, task_service, user_group_service)
    with pytest.raises(NotFoundError):
        task_group_service.assign(task.taskId, "unknown-group", assignee.userId)


def test_assign_raises_if_assignee_missing(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    _, _, group, task = _setup(user_service, group_service, task_service, user_group_service)
    with pytest.raises(NotFoundError):
        task_group_service.assign(task.taskId, group.groupId, "unknown-user")


def test_assign_raises_bad_request_if_assignee_not_group_member(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    _, _, group, task = _setup(user_service, group_service, task_service, user_group_service)
    outsider = user_service.create_user(first_name="Cara", last_name="Jones")
    with pytest.raises(BadRequestError) as exc_info:
        task_group_service.assign(task.taskId, group.groupId, outsider.userId)
    assert exc_info.value.error_code == ErrorCode.ASSIGNEE_NOT_GROUP_MEMBER
    assert exc_info.value.http_code == 400


def test_assign_creates_relationship(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    _, assignee, group, task = _setup(user_service, group_service, task_service, user_group_service)
    relationship = task_group_service.assign(task.taskId, group.groupId, assignee.userId)
    assert relationship.uuid
    assert relationship.taskId == task.taskId
    assert relationship.groupId == group.groupId
    assert relationship.assigneeId == assignee.userId


def test_assign_twice_updates_existing_relationship(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    creator, assignee, group, task = _setup(user_service, group_service, task_service, user_group_service)
    first = task_group_service.assign(task.taskId, group.groupId, assignee.userId)
    second = task_group_service.assign(task.taskId, group.groupId, creator.userId)
    assert first.uuid == second.uuid
    assert second.assigneeId == creator.userId


def test_unassign_clears_assignee(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    _, assignee, group, task = _setup(user_service, group_service, task_service, user_group_service)
    task_group_service.assign(task.taskId, group.groupId, assignee.userId)
    result = task_group_service.unassign(task.taskId, group.groupId, assignee.userId)
    assert result.assigneeId is None


def test_unassign_raises_if_no_matching_assignment(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    _, assignee, group, task = _setup(user_service, group_service, task_service, user_group_service)
    with pytest.raises(NotFoundError):
        task_group_service.unassign(task.taskId, group.groupId, assignee.userId)


def test_unassign_raises_if_assignee_does_not_match_current_assignment(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    creator, assignee, group, task = _setup(user_service, group_service, task_service, user_group_service)
    task_group_service.assign(task.taskId, group.groupId, creator.userId)
    with pytest.raises(NotFoundError):
        task_group_service.unassign(task.taskId, group.groupId, assignee.userId)
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `pytest tests/unit/test_task_group_service.py -v`
Expected: `FAIL` — `ImportError: cannot import name 'BadRequestError' from 'app.exceptions'` (and/or `TypeError` on `TaskGroupService.__init__` missing the new positional arg, since the fixture already passes 5 args).

- [ ] **Step 4: Add `ErrorCode`, `ERROR_CODE_MESSAGES`, `BadRequestError` to `app/exceptions.py`**

Full new content of `app/exceptions.py`:

```python
class NotFoundError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ConflictError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ErrorCode:
    ASSIGNEE_NOT_GROUP_MEMBER = "ERR_TASKS_001"
    TASK_ALREADY_COMPLETED = "ERR_TASKS_002"
    DUPLICATE_GROUP_MEMBERSHIP = "ERR_TASKS_003"


ERROR_CODE_MESSAGES: dict[str, str] = {
    ErrorCode.ASSIGNEE_NOT_GROUP_MEMBER: "Assignee is not a member of the target group",
    ErrorCode.TASK_ALREADY_COMPLETED: "Task is already COMPLETED and cannot be marked COMPLETED again",
    ErrorCode.DUPLICATE_GROUP_MEMBERSHIP: "User is already associated with this group",
}


class BadRequestError(Exception):
    http_code: int = 400

    def __init__(self, error_code: str, message: str | None = None):
        self.error_code = error_code
        self.message = message or ERROR_CODE_MESSAGES.get(error_code, "Bad request")
        super().__init__(self.message)
```

- [ ] **Step 5: Add `is_member` to `UserGroupService`**

In `app/services/user_group_service.py`, add a new method (leave `associate`/`disassociate`/`list_by_group` unchanged in this task — `associate`'s own duplicate-check is Task 3):

```python
    def is_member(self, user_id: str, group_id: str) -> bool:
        return self._repository.find_by_user_and_group(user_id, group_id) is not None
```

Place it after `list_by_group`. Full file after this change:

```python
import uuid

from app.exceptions import NotFoundError
from app.models.user_group import UserGroupRelationship
from app.repositories.user_group_repository import InMemoryUserGroupRepository
from app.services.group_service import GroupService
from app.services.user_service import UserService


class UserGroupService:
    def __init__(
        self,
        repository: InMemoryUserGroupRepository,
        user_service: UserService,
        group_service: GroupService,
    ):
        self._repository = repository
        self._user_service = user_service
        self._group_service = group_service

    def associate(self, user_id: str, group_id: str, relationship: str) -> UserGroupRelationship:
        self._user_service.get_user(user_id)
        self._group_service.get_group(group_id)
        entity = UserGroupRelationship(
            uuid=str(uuid.uuid4()), groupId=group_id, userId=user_id, relationship=relationship
        )
        return self._repository.add(entity)

    def disassociate(self, user_id: str, group_id: str) -> None:
        existing = self._repository.find_by_user_and_group(user_id, group_id)
        if existing is None:
            raise NotFoundError(f"User {user_id} is not associated with group {group_id}")
        self._repository.delete(existing.uuid)

    def list_by_group(self, group_id: str) -> list[UserGroupRelationship]:
        return self._repository.list_by_group(group_id)

    def is_member(self, user_id: str, group_id: str) -> bool:
        return self._repository.find_by_user_and_group(user_id, group_id) is not None
```

- [ ] **Step 6: Update `TaskGroupService` to require membership on assign**

Full new content of `app/services/task_group_service.py`:

```python
import uuid

from app.exceptions import BadRequestError, ErrorCode, NotFoundError
from app.models.task_group import TaskGroupRelationship
from app.repositories.task_group_repository import InMemoryTaskGroupRepository
from app.services.group_service import GroupService
from app.services.task_service import TaskService
from app.services.user_group_service import UserGroupService
from app.services.user_service import UserService


class TaskGroupService:
    def __init__(
        self,
        repository: InMemoryTaskGroupRepository,
        task_service: TaskService,
        group_service: GroupService,
        user_service: UserService,
        user_group_service: UserGroupService,
    ):
        self._repository = repository
        self._task_service = task_service
        self._group_service = group_service
        self._user_service = user_service
        self._user_group_service = user_group_service

    def assign(self, task_id: str, group_id: str, assignee_id: str) -> TaskGroupRelationship:
        self._task_service.get_task(task_id)
        self._group_service.get_group(group_id)
        self._user_service.get_user(assignee_id)
        if not self._user_group_service.is_member(assignee_id, group_id):
            raise BadRequestError(ErrorCode.ASSIGNEE_NOT_GROUP_MEMBER)

        existing = self._repository.find_by_task_and_group(task_id, group_id)
        if existing is not None:
            updated = existing.model_copy(update={"assigneeId": assignee_id})
            return self._repository.update(updated)

        entity = TaskGroupRelationship(
            uuid=str(uuid.uuid4()), taskId=task_id, groupId=group_id, assigneeId=assignee_id
        )
        return self._repository.add(entity)

    def unassign(self, task_id: str, group_id: str, assignee_id: str) -> TaskGroupRelationship:
        existing = self._repository.find_by_task_and_group(task_id, group_id)
        if existing is None or existing.assigneeId != assignee_id:
            raise NotFoundError(
                f"No assignment of user {assignee_id} to task {task_id} in group {group_id}"
            )
        updated = existing.model_copy(update={"assigneeId": None})
        return self._repository.update(updated)
```

- [ ] **Step 7: Update `app/dependencies.py` to pass `user_group_service` into `TaskGroupService`**

Change only the `get_task_group_service` function:

```python
def get_task_group_service() -> TaskGroupService:
    return TaskGroupService(
        get_task_group_repository(),
        get_task_service(),
        get_group_service(),
        get_user_service(),
        get_user_group_service(),
    )
```

(No import changes needed — `get_user_group_service` is already defined earlier in the same file.)

- [ ] **Step 8: Update `tests/conftest.py` to wire `user_group_service` into `TaskGroupService`**

Change only this line inside the `client` fixture:

```python
    task_group_service = TaskGroupService(
        task_group_repo, task_service, group_service, user_service, user_group_service
    )
```

(`user_group_service` is already constructed earlier in the same fixture — no other changes needed.)

- [ ] **Step 9: Run the unit test to verify it passes**

Run: `pytest tests/unit/test_task_group_service.py -v`
Expected: `PASS` (9 passed)

- [ ] **Step 10: Update `app/api/v1/task_group.py` to map `BadRequestError` to HTTP 400**

Full new content:

```python
from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_task_group_service
from app.exceptions import BadRequestError, NotFoundError
from app.schemas.task_group import TaskGroupAssignRequest, TaskGroupResponse
from app.services.task_group_service import TaskGroupService

router = APIRouter(prefix="/api/v1/groups/{group_id}/tasks/{task_id}/assignee", tags=["task-group"])


@router.post("", response_model=TaskGroupResponse, status_code=status.HTTP_201_CREATED)
def assign_task(
    group_id: str,
    task_id: str,
    payload: TaskGroupAssignRequest,
    service: TaskGroupService = Depends(get_task_group_service),
) -> TaskGroupResponse:
    try:
        relationship = service.assign(task_id, group_id, payload.assigneeId)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BadRequestError as exc:
        raise HTTPException(
            status_code=exc.http_code, detail={"errorCode": exc.error_code, "message": exc.message}
        ) from exc
    return TaskGroupResponse(**relationship.model_dump())


@router.delete("/{assignee_id}", response_model=TaskGroupResponse)
def unassign_task(
    group_id: str,
    task_id: str,
    assignee_id: str,
    service: TaskGroupService = Depends(get_task_group_service),
) -> TaskGroupResponse:
    try:
        relationship = service.unassign(task_id, group_id, assignee_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return TaskGroupResponse(**relationship.model_dump())
```

- [ ] **Step 11: Update `tests/integration/test_task_group_api.py`**

Full new content (adds an `_associate_user` helper, associates the assignee before every existing assign call, and adds one new 400 test):

```python
def _create_user(client, first_name="Ada", last_name="Lovelace"):
    return client.post(
        "/api/v1/users", json={"firstName": first_name, "lastName": last_name}
    ).json()["userId"]


def _create_group(client, creator_id):
    return client.post(
        "/api/v1/groups",
        json={"groupName": "Smiths", "groupCategory": "Family", "groupCreaterId": creator_id},
    ).json()["groupId"]


def _create_task(client, creator_id):
    return client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": creator_id}
    ).json()["taskId"]


def _associate_user(client, group_id, user_id, relationship="Member"):
    return client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": user_id, "relationship": relationship}
    )


def test_assign_task_to_group_member(client):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)
    task_id = _create_task(client, creator_id)
    _associate_user(client, group_id, creator_id, "Creator")

    response = client.post(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": creator_id}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["taskId"] == task_id
    assert body["groupId"] == group_id
    assert body["assigneeId"] == creator_id


def test_assign_task_unknown_assignee_returns_404(client):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)
    task_id = _create_task(client, creator_id)

    response = client.post(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": "unknown"}
    )
    assert response.status_code == 404


def test_assign_task_to_non_member_returns_400(client):
    creator_id = _create_user(client)
    outsider_id = _create_user(client, first_name="Cara", last_name="Jones")
    group_id = _create_group(client, creator_id)
    task_id = _create_task(client, creator_id)

    response = client.post(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": outsider_id}
    )
    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["errorCode"] == "ERR_TASKS_001"


def test_unassign_task(client):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)
    task_id = _create_task(client, creator_id)
    _associate_user(client, group_id, creator_id, "Creator")
    client.post(f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": creator_id})

    response = client.delete(f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee/{creator_id}")
    assert response.status_code == 200
    assert response.json()["assigneeId"] is None


def test_unassign_task_without_prior_assignment_returns_404(client):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)
    task_id = _create_task(client, creator_id)

    response = client.delete(f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee/{creator_id}")
    assert response.status_code == 404


def test_unassign_task_with_mismatched_assignee_returns_404(client):
    creator_id = _create_user(client)
    other_user_id = _create_user(client, first_name="Bob", last_name="Smith")
    group_id = _create_group(client, creator_id)
    task_id = _create_task(client, creator_id)
    _associate_user(client, group_id, creator_id, "Creator")
    client.post(f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": creator_id})

    response = client.delete(f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee/{other_user_id}")
    assert response.status_code == 404
```

Note: `test_unassign_task_with_mismatched_assignee_returns_404` only needs `creator_id` to be a member (it's the one being assigned); `other_user_id` never needs to be a member since it's only used as the (wrong) unassign target, which fails on the mismatch check before any membership concern would apply.

- [ ] **Step 12: Run the integration tests, then the full suite**

Run: `pytest tests/integration/test_task_group_api.py -v`
Expected: `PASS` (7 passed)

Run: `pytest -v`
Expected: all tests pass except `tests/integration/test_full_lifecycle_api.py` — verify it too, since it already associates the member before assigning (see plan Context); it should already pass unchanged. If it fails, re-check `_associate` ordering in that file before treating it as a regression to fix elsewhere.

- [ ] **Step 13: Commit**

```bash
git add app/exceptions.py app/services/task_group_service.py app/services/user_group_service.py \
        app/api/v1/task_group.py app/dependencies.py tests/conftest.py \
        tests/unit/test_task_group_service.py tests/integration/test_task_group_api.py
git commit -m "feat: reject task assignment to non-group-members with ERR_TASKS_001"
```

---

## Task 2: Rule (b) — reject re-completing an already-`COMPLETED` task

**Files:**
- Modify: `app/services/task_service.py`
- Modify: `app/api/v1/tasks.py`
- Test: `tests/unit/test_task_service.py`
- Test: `tests/integration/test_tasks_api.py`

**Interfaces:**
- Consumes: `BadRequestError`, `ErrorCode` from `app/exceptions.py` (Task 1).
- No new interfaces produced — this task only changes `TaskService.update_task_state`'s internal validation.

- [ ] **Step 1: Write the failing unit tests**

Add these two tests to `tests/unit/test_task_service.py` (after `test_update_task_state_transitions`, before `test_update_due_date`), and add `BadRequestError, ErrorCode` to the existing `from app.exceptions import NotFoundError` import line:

```python
from app.exceptions import BadRequestError, ErrorCode, NotFoundError
```

```python
def test_update_task_state_raises_bad_request_if_already_completed(
    task_service: TaskService, user_service: UserService
):
    user = user_service.create_user(first_name="Ada", last_name="Lovelace")
    task = task_service.create_task(task_title="Buy milk", created_by=user.userId)
    task_service.update_task_state(task.taskId, updated_by=user.userId, new_state=TaskState.COMPLETED)
    with pytest.raises(BadRequestError) as exc_info:
        task_service.update_task_state(task.taskId, updated_by=user.userId, new_state=TaskState.COMPLETED)
    assert exc_info.value.error_code == ErrorCode.TASK_ALREADY_COMPLETED
    assert exc_info.value.http_code == 400


def test_update_task_state_allows_moving_out_of_completed(
    task_service: TaskService, user_service: UserService
):
    user = user_service.create_user(first_name="Ada", last_name="Lovelace")
    task = task_service.create_task(task_title="Buy milk", created_by=user.userId)
    task_service.update_task_state(task.taskId, updated_by=user.userId, new_state=TaskState.COMPLETED)
    updated = task_service.update_task_state(
        task.taskId, updated_by=user.userId, new_state=TaskState.TODO
    )
    assert updated.taskState == TaskState.TODO
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/unit/test_task_service.py -v`
Expected: `FAIL` — `test_update_task_state_raises_bad_request_if_already_completed` fails because no `BadRequestError` is raised (the current code allows `COMPLETED` → `COMPLETED` silently).

- [ ] **Step 3: Add the re-completion guard to `TaskService.update_task_state`**

In `app/services/task_service.py`, update the import line and the method body:

```python
from app.exceptions import BadRequestError, ErrorCode, NotFoundError
```

```python
    def update_task_state(self, task_id: str, updated_by: str, new_state: TaskState) -> Task:
        self._user_service.get_user(updated_by)
        task = self.get_task(task_id)
        if task.taskState == TaskState.COMPLETED and new_state == TaskState.COMPLETED:
            raise BadRequestError(ErrorCode.TASK_ALREADY_COMPLETED)
        updated = task.model_copy(
            update={
                "taskState": new_state,
                "updatedBy": updated_by,
                "updatedAt": datetime.now(timezone.utc),
            }
        )
        return self._repository.update(updated)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/unit/test_task_service.py -v`
Expected: `PASS` (8 passed)

- [ ] **Step 5: Update `app/api/v1/tasks.py` to map `BadRequestError` to HTTP 400 for the state endpoint**

Update the import line and `update_task_state`:

```python
from app.exceptions import BadRequestError, NotFoundError
```

```python
@router.patch("/{task_id}/state", response_model=TaskResponse)
def update_task_state(
    task_id: str, payload: TaskStateUpdateRequest, service: TaskService = Depends(get_task_service)
) -> TaskResponse:
    try:
        task = service.update_task_state(task_id, updated_by=payload.updatedBy, new_state=payload.taskState)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BadRequestError as exc:
        raise HTTPException(
            status_code=exc.http_code, detail={"errorCode": exc.error_code, "message": exc.message}
        ) from exc
    return _to_response(task)
```

(Leave `create_task`, `get_task`, `update_task_meta`, `update_due_date` untouched — none of them can raise `BadRequestError`.)

- [ ] **Step 6: Write the failing integration tests**

Add to `tests/integration/test_tasks_api.py` (after `test_update_task_state`):

```python
def test_update_task_state_already_completed_returns_400(client):
    user_id = _create_user(client)
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": user_id}
    ).json()["taskId"]
    client.patch(f"/api/v1/tasks/{task_id}/state", json={"updatedBy": user_id, "taskState": "COMPLETED"})

    response = client.patch(
        f"/api/v1/tasks/{task_id}/state", json={"updatedBy": user_id, "taskState": "COMPLETED"}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["errorCode"] == "ERR_TASKS_002"


def test_update_task_state_allows_moving_out_of_completed(client):
    user_id = _create_user(client)
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": user_id}
    ).json()["taskId"]
    client.patch(f"/api/v1/tasks/{task_id}/state", json={"updatedBy": user_id, "taskState": "COMPLETED"})

    response = client.patch(
        f"/api/v1/tasks/{task_id}/state", json={"updatedBy": user_id, "taskState": "TODO"}
    )
    assert response.status_code == 200
    assert response.json()["taskState"] == "TODO"
```

- [ ] **Step 7: Run the integration tests, then the full suite**

Run: `pytest tests/integration/test_tasks_api.py -v`
Expected: `PASS` (6 passed)

Run: `pytest -v`
Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add app/services/task_service.py app/api/v1/tasks.py \
        tests/unit/test_task_service.py tests/integration/test_tasks_api.py
git commit -m "feat: reject re-completing an already-COMPLETED task with ERR_TASKS_002"
```

---

## Task 3: Rule (c) — reject duplicate user-group association

**Files:**
- Modify: `app/services/user_group_service.py`
- Modify: `app/api/v1/user_group.py`
- Test: `tests/unit/test_user_group_service.py`
- Test: `tests/integration/test_user_group_api.py`

**Interfaces:**
- Consumes: `BadRequestError`, `ErrorCode` from `app/exceptions.py` (Task 1); `UserGroupService.is_member` (Task 1, reused here so `associate` doesn't duplicate the lookup logic already added).

- [ ] **Step 1: Write the failing unit test**

Add to `tests/unit/test_user_group_service.py` (after `test_associate_creates_relationship`), and add `BadRequestError, ErrorCode` to the existing import line:

```python
from app.exceptions import BadRequestError, ErrorCode, NotFoundError
```

```python
def test_associate_raises_bad_request_if_already_associated(
    user_group_service: UserGroupService, group_service, user_service
):
    user, group = _make_user_and_group(user_service, group_service)
    user_group_service.associate(user.userId, group.groupId, "Father")
    with pytest.raises(BadRequestError) as exc_info:
        user_group_service.associate(user.userId, group.groupId, "Father")
    assert exc_info.value.error_code == ErrorCode.DUPLICATE_GROUP_MEMBERSHIP
    assert exc_info.value.http_code == 400
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/unit/test_user_group_service.py -v`
Expected: `FAIL` — no `BadRequestError` is raised, `associate` succeeds twice.

- [ ] **Step 3: Add the duplicate-membership guard to `UserGroupService.associate`**

Full new content of `app/services/user_group_service.py`:

```python
import uuid

from app.exceptions import BadRequestError, ErrorCode, NotFoundError
from app.models.user_group import UserGroupRelationship
from app.repositories.user_group_repository import InMemoryUserGroupRepository
from app.services.group_service import GroupService
from app.services.user_service import UserService


class UserGroupService:
    def __init__(
        self,
        repository: InMemoryUserGroupRepository,
        user_service: UserService,
        group_service: GroupService,
    ):
        self._repository = repository
        self._user_service = user_service
        self._group_service = group_service

    def associate(self, user_id: str, group_id: str, relationship: str) -> UserGroupRelationship:
        self._user_service.get_user(user_id)
        self._group_service.get_group(group_id)
        if self.is_member(user_id, group_id):
            raise BadRequestError(ErrorCode.DUPLICATE_GROUP_MEMBERSHIP)
        entity = UserGroupRelationship(
            uuid=str(uuid.uuid4()), groupId=group_id, userId=user_id, relationship=relationship
        )
        return self._repository.add(entity)

    def disassociate(self, user_id: str, group_id: str) -> None:
        existing = self._repository.find_by_user_and_group(user_id, group_id)
        if existing is None:
            raise NotFoundError(f"User {user_id} is not associated with group {group_id}")
        self._repository.delete(existing.uuid)

    def list_by_group(self, group_id: str) -> list[UserGroupRelationship]:
        return self._repository.list_by_group(group_id)

    def is_member(self, user_id: str, group_id: str) -> bool:
        return self._repository.find_by_user_and_group(user_id, group_id) is not None
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/unit/test_user_group_service.py -v`
Expected: `PASS` (7 passed)

- [ ] **Step 5: Update `app/api/v1/user_group.py` to map `BadRequestError` to HTTP 400**

Full new content:

```python
from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_user_group_service
from app.exceptions import BadRequestError, NotFoundError
from app.schemas.user_group import UserGroupAssociateRequest, UserGroupResponse
from app.services.user_group_service import UserGroupService

router = APIRouter(prefix="/api/v1/groups", tags=["user-group"])


@router.post(
    "/{group_id}/members", response_model=UserGroupResponse, status_code=status.HTTP_201_CREATED
)
def associate_user(
    group_id: str,
    payload: UserGroupAssociateRequest,
    service: UserGroupService = Depends(get_user_group_service),
) -> UserGroupResponse:
    try:
        relationship = service.associate(payload.userId, group_id, payload.relationship)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BadRequestError as exc:
        raise HTTPException(
            status_code=exc.http_code, detail={"errorCode": exc.error_code, "message": exc.message}
        ) from exc
    return UserGroupResponse(**relationship.model_dump())


@router.delete("/{group_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def disassociate_user(
    group_id: str, user_id: str, service: UserGroupService = Depends(get_user_group_service)
) -> None:
    try:
        service.disassociate(user_id, group_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
```

- [ ] **Step 6: Write the failing integration test**

Add to `tests/integration/test_user_group_api.py` (after `test_associate_user_to_group`):

```python
def test_associate_duplicate_returns_400(client):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)
    client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": creator_id, "relationship": "Father"}
    )

    response = client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": creator_id, "relationship": "Father"}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["errorCode"] == "ERR_TASKS_003"
```

- [ ] **Step 7: Run the integration tests, then the full suite**

Run: `pytest tests/integration/test_user_group_api.py -v`
Expected: `PASS` (5 passed)

Run: `pytest -v`
Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add app/services/user_group_service.py app/api/v1/user_group.py \
        tests/unit/test_user_group_service.py tests/integration/test_user_group_api.py
git commit -m "feat: reject duplicate user-group association with ERR_TASKS_003"
```

---

## Task 4: Update `OpenPoints.md` and final full-suite verification

**Files:**
- Modify: `OpenPoints.md`

**Interfaces:** None — documentation only.

- [ ] **Step 1: Update the "Validation gaps" section of `OpenPoints.md`**

Replace the three now-fixed bullets (assignee-membership, unrestricted state transitions, duplicate-association) with notes that they're resolved and a pointer to the new error-code mechanism. Replace the entire "## Validation gaps" section with:

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

- [ ] **Step 2: Run the full test suite one final time**

Run: `pytest -v`
Expected: all tests pass — the suite should now be 54 (previous count) + 3 new BadRequestError unit tests + 1 allowed-transition unit test + 3 new BadRequestError integration tests + 1 allowed-transition integration test = 62 passing (exact count may drift slightly depending on final fixture wiring; treat "0 failures, pristine output" as the real bar, not the exact number).

- [ ] **Step 3: Commit**

```bash
git add OpenPoints.md
git commit -m "docs: mark validation gaps (a)/(b)/(c) resolved in OpenPoints.md"
```

---

## Verification (end-to-end)

1. `pytest -v` — full suite green, 0 failures, pristine output (no warnings).
2. Start the server (`uvicorn app.main:app --reload`) and manually verify each new 400 path with `curl`:
   - Create two users and a group (first user as creator); assign a task to the second user *without* associating them first → expect `400` with `{"detail": {"errorCode": "ERR_TASKS_001", ...}}`.
   - Create a task, move it to `COMPLETED`, then PATCH `.../state` to `COMPLETED` again → expect `400` with `ERR_TASKS_002`. Then PATCH `.../state` to `TODO` → expect `200` (confirms the narrower rule).
   - Associate a user to a group, then associate the same user to the same group again → expect `400` with `ERR_TASKS_003`.
3. Confirm `OpenPoints.md`'s "Validation gaps" section accurately reflects the three fixes and the new error-code table.
