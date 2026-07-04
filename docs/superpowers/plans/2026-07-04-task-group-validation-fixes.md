# Task/Group Validation Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the three validation fixes in `ASK.md`: reject no-op task state transitions, forbid assigning a task to its own creator, and forbid a group's creator from becoming a member of their own group.

**Architecture:** Each fix is a single new/broadened check inside an existing service method (`TaskService.update_task_state`, `TaskGroupService.assign`, `UserGroupService.associate`), raising the existing `BadRequestError`/`ErrorCode` pattern already used throughout the codebase. No new files, no schema changes. The two "creator" rules ripple into several existing tests that currently use a group's/task's creator as a stand-in member/assignee for convenience — those are fixed as part of the same task that introduces the rule.

**Tech Stack:** Same as the rest of the app — FastAPI, Pydantic, pytest, real PostgreSQL via the `db_session` fixture in `tests/conftest.py`.

## Global Constraints

- Resolved with the user: the COMPLETED→COMPLETED case must return `ERR_TASKS_002`, not a separate `ERR_TASKS_004`. `ErrorCode.TASK_ALREADY_COMPLETED` is renamed to `TASK_ALREADY_IN_REQUESTED_STATE` (still string value `"ERR_TASKS_002"`) and broadened to cover *any* no-op state transition, with its message updated. `ERR_TASKS_004` is intentionally never introduced — this must be documented in `OpenPoints.md` so it doesn't look like an oversight.
- New codes: `ERR_TASKS_005` (`TASK_CREATOR_CANNOT_BE_ASSIGNEE`), `ERR_TASKS_006` (`GROUP_CREATOR_CANNOT_BE_MEMBER`) — exact strings from `ASK.md`.
- Where a new check and an existing check could both fire for the same input (e.g. the creator is also never a group member, so they'd fail the plain "not a group member" check too), the more specific new check must run first so the client gets the more informative error code — same precedent as the `ERR_TASKS_002` resolution above.
- Don't change anything about `TaskGroupService.unassign`'s "update, never delete" semantics (unrelated, already correct).

---

## Task 1: Generalize the "already in requested state" check

**Files:**
- Modify: `app/exceptions.py`
- Modify: `app/services/task_service.py`
- Modify: `tests/unit/test_task_service.py`
- Modify: `tests/integration/test_tasks_api.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `ErrorCode.TASK_ALREADY_IN_REQUESTED_STATE = "ERR_TASKS_002"` (renamed from `TASK_ALREADY_COMPLETED`) — Task 2/3 don't touch this, but any future code referencing the old name must use the new one.

- [ ] **Step 1: Write the failing unit test for the new general case**

Add to `tests/unit/test_task_service.py`, after `test_update_task_state_raises_bad_request_if_already_completed`:
```python
def test_update_task_state_raises_bad_request_if_same_state_requested(
    task_service: TaskService, user_service: UserService
):
    user = user_service.create_user(first_name="Ada", last_name="Lovelace")
    task = task_service.create_task(task_title="Buy milk", created_by=user.userId)
    with pytest.raises(BadRequestError) as exc_info:
        task_service.update_task_state(task.taskId, updated_by=user.userId, new_state=TaskState.TODO)
    assert exc_info.value.error_code == ErrorCode.TASK_ALREADY_IN_REQUESTED_STATE
    assert exc_info.value.http_code == 400
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_task_service.py::test_update_task_state_raises_bad_request_if_same_state_requested -v`
Expected: FAIL — a freshly created task defaults to `TODO`, and today `update_task_state(..., new_state=TODO)` succeeds silently (200, not a 400) since only the COMPLETED→COMPLETED case is checked.

- [ ] **Step 3: Rename and broaden the error code**

In `app/exceptions.py`, change:
```python
class ErrorCode:
    ASSIGNEE_NOT_GROUP_MEMBER = "ERR_TASKS_001"
    TASK_ALREADY_COMPLETED = "ERR_TASKS_002"
    DUPLICATE_GROUP_MEMBERSHIP = "ERR_TASKS_003"


ERROR_CODE_MESSAGES: dict[str, str] = {
    ErrorCode.ASSIGNEE_NOT_GROUP_MEMBER: "Assignee is not a member of the target group",
    ErrorCode.TASK_ALREADY_COMPLETED: "Task is already COMPLETED and cannot be marked COMPLETED again",
    ErrorCode.DUPLICATE_GROUP_MEMBERSHIP: "User is already associated with this group",
}
```
to:
```python
class ErrorCode:
    ASSIGNEE_NOT_GROUP_MEMBER = "ERR_TASKS_001"
    TASK_ALREADY_IN_REQUESTED_STATE = "ERR_TASKS_002"
    DUPLICATE_GROUP_MEMBERSHIP = "ERR_TASKS_003"
    TASK_CREATOR_CANNOT_BE_ASSIGNEE = "ERR_TASKS_005"
    GROUP_CREATOR_CANNOT_BE_MEMBER = "ERR_TASKS_006"


ERROR_CODE_MESSAGES: dict[str, str] = {
    ErrorCode.ASSIGNEE_NOT_GROUP_MEMBER: "Assignee is not a member of the target group",
    ErrorCode.TASK_ALREADY_IN_REQUESTED_STATE: "Task is already in the requested state",
    ErrorCode.DUPLICATE_GROUP_MEMBERSHIP: "User is already associated with this group",
    ErrorCode.TASK_CREATOR_CANNOT_BE_ASSIGNEE: "Task creator cannot be assigned to their own task",
    ErrorCode.GROUP_CREATOR_CANNOT_BE_MEMBER: "Group creator cannot be a member of their own group",
}
```
(`ERR_TASKS_004` is intentionally never defined — see Task 4's `OpenPoints.md` update for why.)

- [ ] **Step 4: Broaden the check in `TaskService.update_task_state`**

In `app/services/task_service.py`, change:
```python
    def update_task_state(self, task_id: str, updated_by: str, new_state: TaskState) -> Task:
        self._user_service.get_user(updated_by)
        task = self.get_task(task_id)
        if task.taskState == TaskState.COMPLETED and new_state == TaskState.COMPLETED:
            raise BadRequestError(ErrorCode.TASK_ALREADY_COMPLETED)
```
to:
```python
    def update_task_state(self, task_id: str, updated_by: str, new_state: TaskState) -> Task:
        self._user_service.get_user(updated_by)
        task = self.get_task(task_id)
        if task.taskState == new_state:
            raise BadRequestError(ErrorCode.TASK_ALREADY_IN_REQUESTED_STATE)
```

- [ ] **Step 5: Update the existing unit test's assertion**

In `tests/unit/test_task_service.py`, in `test_update_task_state_raises_bad_request_if_already_completed`, change:
```python
    assert exc_info.value.error_code == ErrorCode.TASK_ALREADY_COMPLETED
```
to:
```python
    assert exc_info.value.error_code == ErrorCode.TASK_ALREADY_IN_REQUESTED_STATE
```

- [ ] **Step 6: Run both unit tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_task_service.py -v`
Expected: PASS — all tests in the file, including both the existing (now-renamed) and new same-state tests.

- [ ] **Step 7: Add an integration test for the new general case**

Add to the end of `tests/integration/test_tasks_api.py`:
```python
def test_update_task_state_same_state_returns_400(client):
    user_id = _create_user(client)
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": user_id}
    ).json()["taskId"]

    response = client.patch(
        f"/api/v1/tasks/{task_id}/state", json={"updatedBy": user_id, "taskState": "TODO"}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["errorCode"] == "ERR_TASKS_002"
```

- [ ] **Step 8: Run the full integration file**

Run: `.venv/bin/pytest tests/integration/test_tasks_api.py -v`
Expected: PASS — including the pre-existing `test_update_task_state_already_completed_returns_400`, whose assertion (`errorCode == "ERR_TASKS_002"`) is a literal string and needs no change since the *value* of `ERR_TASKS_002` didn't change, only its Python constant name and scope.

- [ ] **Step 9: Commit**

```bash
git add app/exceptions.py app/services/task_service.py tests/unit/test_task_service.py tests/integration/test_tasks_api.py
git commit -m "feat: reject any no-op task state transition, not just COMPLETED->COMPLETED"
```

---

## Task 2: Group creator cannot be a member of their own group

**Files:**
- Modify: `app/services/user_group_service.py`
- Modify: `tests/unit/test_user_group_service.py`
- Modify: `tests/unit/test_task_group_service.py` (fixture ripple only — its `_setup` helper currently associates the creator as a member)
- Modify: `tests/integration/test_user_group_api.py`
- Modify: `tests/integration/test_task_group_api.py` (fixture ripple only)

**Interfaces:**
- Consumes: `ErrorCode.GROUP_CREATOR_CANNOT_BE_MEMBER` (Task 1).
- Produces: `UserGroupService.associate` now raises `BadRequestError(ErrorCode.GROUP_CREATOR_CANNOT_BE_MEMBER)` when `user_id == group.groupCreaterId`. Every later task that needs "a group member" fixture must use a user distinct from the group's creator — Task 3 relies on this.

- [ ] **Step 1: Write the failing unit test**

Add to `tests/unit/test_user_group_service.py`, after `test_associate_raises_if_group_missing`:
```python
def test_associate_raises_bad_request_if_user_is_group_creator(
    user_group_service: UserGroupService, group_service, user_service
):
    creator, group = _make_user_and_group(user_service, group_service)
    with pytest.raises(BadRequestError) as exc_info:
        user_group_service.associate(creator.userId, group.groupId, "Father")
    assert exc_info.value.error_code == ErrorCode.GROUP_CREATOR_CANNOT_BE_MEMBER
    assert exc_info.value.http_code == 400
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_user_group_service.py::test_associate_raises_bad_request_if_user_is_group_creator -v`
Expected: FAIL — today `associate(creator.userId, ...)` succeeds (201-equivalent), since nothing stops a creator from also being a member.

- [ ] **Step 3: Add the check in `UserGroupService.associate`**

In `app/services/user_group_service.py`, change:
```python
    def associate(self, user_id: str, group_id: str, relationship: str) -> UserGroupRelationship:
        self._user_service.get_user(user_id)
        self._group_service.get_group(group_id)
        if self.is_member(user_id, group_id):
            raise BadRequestError(ErrorCode.DUPLICATE_GROUP_MEMBERSHIP)
```
to:
```python
    def associate(self, user_id: str, group_id: str, relationship: str) -> UserGroupRelationship:
        self._user_service.get_user(user_id)
        group = self._group_service.get_group(group_id)
        if user_id == group.groupCreaterId:
            raise BadRequestError(ErrorCode.GROUP_CREATOR_CANNOT_BE_MEMBER)
        if self.is_member(user_id, group_id):
            raise BadRequestError(ErrorCode.DUPLICATE_GROUP_MEMBERSHIP)
```

- [ ] **Step 4: Run the new test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_user_group_service.py::test_associate_raises_bad_request_if_user_is_group_creator -v`
Expected: PASS

- [ ] **Step 5: Fix the now-broken existing unit tests**

Four existing tests in `tests/unit/test_user_group_service.py` currently associate the group's own creator (from `_make_user_and_group`) as a "member," which the new rule now forbids. Fix each by introducing a second, non-creator user.

Change:
```python
def test_associate_creates_relationship(user_group_service: UserGroupService, group_service, user_service):
    user, group = _make_user_and_group(user_service, group_service)
    relationship = user_group_service.associate(user.userId, group.groupId, "Father")
    assert relationship.uuid
    assert relationship.userId == user.userId
    assert relationship.groupId == group.groupId
    assert relationship.relationship == "Father"
```
to:
```python
def test_associate_creates_relationship(user_group_service: UserGroupService, group_service, user_service):
    _, group = _make_user_and_group(user_service, group_service)
    member = user_service.create_user(first_name="Bob", last_name="Smith")
    relationship = user_group_service.associate(member.userId, group.groupId, "Father")
    assert relationship.uuid
    assert relationship.userId == member.userId
    assert relationship.groupId == group.groupId
    assert relationship.relationship == "Father"
```

Change:
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
to:
```python
def test_associate_raises_bad_request_if_already_associated(
    user_group_service: UserGroupService, group_service, user_service
):
    _, group = _make_user_and_group(user_service, group_service)
    member = user_service.create_user(first_name="Bob", last_name="Smith")
    user_group_service.associate(member.userId, group.groupId, "Father")
    with pytest.raises(BadRequestError) as exc_info:
        user_group_service.associate(member.userId, group.groupId, "Father")
    assert exc_info.value.error_code == ErrorCode.DUPLICATE_GROUP_MEMBERSHIP
    assert exc_info.value.http_code == 400
```

Change:
```python
def test_disassociate_removes_relationship(user_group_service: UserGroupService, group_service, user_service):
    user, group = _make_user_and_group(user_service, group_service)
    user_group_service.associate(user.userId, group.groupId, "Father")
    user_group_service.disassociate(user.userId, group.groupId)
    assert user_group_service.list_by_group(group.groupId) == []
```
to:
```python
def test_disassociate_removes_relationship(user_group_service: UserGroupService, group_service, user_service):
    _, group = _make_user_and_group(user_service, group_service)
    member = user_service.create_user(first_name="Bob", last_name="Smith")
    user_group_service.associate(member.userId, group.groupId, "Father")
    user_group_service.disassociate(member.userId, group.groupId)
    assert user_group_service.list_by_group(group.groupId) == []
```

Change:
```python
def test_list_by_group_returns_members(user_group_service: UserGroupService, group_service, user_service):
    user, group = _make_user_and_group(user_service, group_service)
    user_group_service.associate(user.userId, group.groupId, "Father")

    members = user_group_service.list_by_group(group.groupId)

    assert len(members) == 1
    assert members[0].userId == user.userId
    assert members[0].groupId == group.groupId
    assert members[0].relationship == "Father"
```
to:
```python
def test_list_by_group_returns_members(user_group_service: UserGroupService, group_service, user_service):
    _, group = _make_user_and_group(user_service, group_service)
    member = user_service.create_user(first_name="Bob", last_name="Smith")
    user_group_service.associate(member.userId, group.groupId, "Father")

    members = user_group_service.list_by_group(group.groupId)

    assert len(members) == 1
    assert members[0].userId == member.userId
    assert members[0].groupId == group.groupId
    assert members[0].relationship == "Father"
```

- [ ] **Step 6: Run the full unit test file**

Run: `.venv/bin/pytest tests/unit/test_user_group_service.py -v`
Expected: PASS — all 10 tests (8 original + `test_disassociate_raises_if_not_associated`/`test_associate_raises_if_user_missing`/`test_associate_raises_if_group_missing`/`test_list_by_group_raises_if_group_missing` unaffected, plus the 4 fixed ones, plus the new one).

- [ ] **Step 7: Fix the `_setup` fixture ripple in `tests/unit/test_task_group_service.py`**

The shared `_setup` helper associates the group's creator as a member, which now fails. Change:
```python
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
```
to:
```python
def _setup(user_service, group_service, task_service, user_group_service):
    creator = user_service.create_user(first_name="Ada", last_name="Lovelace")
    assignee = user_service.create_user(first_name="Bob", last_name="Smith")
    group = group_service.create_group(
        group_name="Smiths", group_desc=None, group_category="Family", creater_id=creator.userId
    )
    task = task_service.create_task(task_title="Buy milk", created_by=creator.userId)
    user_group_service.associate(assignee.userId, group.groupId, "Member")
    return creator, assignee, group, task
```
(The creator was never actually needed as a group member by any `TaskGroupService` logic — only the assignee's membership is checked.)

- [ ] **Step 8: Fix the two tests that reassign/unassign using the creator**

`test_assign_twice_updates_existing_relationship` reassigns to the creator, which was only reachable before because `_setup` used to make the creator a member. Change:
```python
def test_assign_twice_updates_existing_relationship(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    creator, assignee, group, task = _setup(user_service, group_service, task_service, user_group_service)
    first = task_group_service.assign(task.taskId, group.groupId, assignee.userId)
    second = task_group_service.assign(task.taskId, group.groupId, creator.userId)
    assert first.uuid == second.uuid
    assert second.assigneeId == creator.userId
```
to:
```python
def test_assign_twice_updates_existing_relationship(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    creator, assignee, group, task = _setup(user_service, group_service, task_service, user_group_service)
    other_member = user_service.create_user(first_name="Cara", last_name="Jones")
    user_group_service.associate(other_member.userId, group.groupId, "Member")
    first = task_group_service.assign(task.taskId, group.groupId, assignee.userId)
    second = task_group_service.assign(task.taskId, group.groupId, other_member.userId)
    assert first.uuid == second.uuid
    assert second.assigneeId == other_member.userId
```

`test_unassign_raises_if_assignee_does_not_match_current_assignment` assigns to the creator first. Change:
```python
def test_unassign_raises_if_assignee_does_not_match_current_assignment(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    creator, assignee, group, task = _setup(user_service, group_service, task_service, user_group_service)
    task_group_service.assign(task.taskId, group.groupId, creator.userId)
    with pytest.raises(NotFoundError):
        task_group_service.unassign(task.taskId, group.groupId, assignee.userId)
```
to:
```python
def test_unassign_raises_if_assignee_does_not_match_current_assignment(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    creator, assignee, group, task = _setup(user_service, group_service, task_service, user_group_service)
    task_group_service.assign(task.taskId, group.groupId, assignee.userId)
    with pytest.raises(NotFoundError):
        task_group_service.unassign(task.taskId, group.groupId, creator.userId)
```
(Swaps which variable plays "assigned" vs. "mismatched" — same test intent, using the already-valid `assignee` as the real assignment and `creator` — who was never a member and now can never be one — as the deliberately-wrong id.)

- [ ] **Step 9: Run the full unit test file**

Run: `.venv/bin/pytest tests/unit/test_task_group_service.py -v`
Expected: PASS — all 9 tests.

- [ ] **Step 10: Fix `tests/integration/test_user_group_api.py`**

Replace the entire file with:
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


def test_associate_user_to_group(client):
    creator_id = _create_user(client)
    member_id = _create_user(client, first_name="Bob", last_name="Smith")
    group_id = _create_group(client, creator_id)

    response = client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": member_id, "relationship": "Father"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["userId"] == member_id
    assert body["groupId"] == group_id
    assert body["relationship"] == "Father"


def test_associate_duplicate_returns_400(client):
    creator_id = _create_user(client)
    member_id = _create_user(client, first_name="Bob", last_name="Smith")
    group_id = _create_group(client, creator_id)
    client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": member_id, "relationship": "Father"}
    )

    response = client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": member_id, "relationship": "Father"}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["errorCode"] == "ERR_TASKS_003"


def test_associate_unknown_user_returns_404(client):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)

    response = client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": "unknown", "relationship": "Father"}
    )
    assert response.status_code == 404


def test_associate_group_creator_returns_400(client):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)

    response = client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": creator_id, "relationship": "Father"}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["errorCode"] == "ERR_TASKS_006"


def test_disassociate_user_from_group(client):
    creator_id = _create_user(client)
    member_id = _create_user(client, first_name="Bob", last_name="Smith")
    group_id = _create_group(client, creator_id)
    client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": member_id, "relationship": "Father"}
    )

    response = client.delete(f"/api/v1/groups/{group_id}/members/{member_id}")
    assert response.status_code == 204


def test_disassociate_unknown_association_returns_404(client):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)

    response = client.delete(f"/api/v1/groups/{group_id}/members/{creator_id}")
    assert response.status_code == 404


def test_get_group_members_returns_associated_users(client):
    creator_id = _create_user(client)
    member_id = _create_user(client, first_name="Bob", last_name="Smith")
    group_id = _create_group(client, creator_id)
    client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": member_id, "relationship": "Father"}
    )

    response = client.get(f"/api/v1/groups/{group_id}/members")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["userId"] == member_id
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

- [ ] **Step 11: Fix `tests/integration/test_task_group_api.py`**

Replace the entire file with:
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
    member_id = _create_user(client, first_name="Bob", last_name="Smith")
    group_id = _create_group(client, creator_id)
    task_id = _create_task(client, creator_id)
    _associate_user(client, group_id, member_id)

    response = client.post(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": member_id}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["taskId"] == task_id
    assert body["groupId"] == group_id
    assert body["assigneeId"] == member_id


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
    member_id = _create_user(client, first_name="Bob", last_name="Smith")
    group_id = _create_group(client, creator_id)
    task_id = _create_task(client, creator_id)
    _associate_user(client, group_id, member_id)
    client.post(f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": member_id})

    response = client.delete(f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee/{member_id}")
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
    member_id = _create_user(client, first_name="Bob", last_name="Smith")
    other_user_id = _create_user(client, first_name="Cara", last_name="Jones")
    group_id = _create_group(client, creator_id)
    task_id = _create_task(client, creator_id)
    _associate_user(client, group_id, member_id)
    client.post(f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": member_id})

    response = client.delete(f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee/{other_user_id}")
    assert response.status_code == 404
```

- [ ] **Step 12: Run both integration files and the full suite**

Run: `.venv/bin/pytest tests/integration/test_user_group_api.py tests/integration/test_task_group_api.py -v`
Expected: PASS — all tests.

Run: `.venv/bin/pytest -v`
Expected: PASS — the full suite, confirming `test_full_lifecycle_api.py` (which already uses a separate `member_id` distinct from the creator) is unaffected.

- [ ] **Step 13: Commit**

```bash
git add app/services/user_group_service.py tests/unit/test_user_group_service.py tests/unit/test_task_group_service.py tests/integration/test_user_group_api.py tests/integration/test_task_group_api.py
git commit -m "feat: forbid a group's creator from being a member of their own group"
```

---

## Task 3: Task cannot be assigned to its own creator

**Files:**
- Modify: `app/services/task_group_service.py`
- Modify: `tests/unit/test_task_group_service.py`
- Modify: `tests/integration/test_task_group_api.py`

**Interfaces:**
- Consumes: `ErrorCode.TASK_CREATOR_CANNOT_BE_ASSIGNEE` (Task 1), the fixed `_setup`/`_create_user` fixtures (Task 2).
- Produces: `TaskGroupService.assign` now raises `BadRequestError(ErrorCode.TASK_CREATOR_CANNOT_BE_ASSIGNEE)` when `assignee_id == task.createdBy`. Terminal task for the service layer — no later task depends on this.

- [ ] **Step 1: Write the failing unit test**

Add to `tests/unit/test_task_group_service.py`, after `test_assign_raises_bad_request_if_assignee_not_group_member`:
```python
def test_assign_raises_bad_request_if_assignee_is_task_creator(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    creator, assignee, group, task = _setup(user_service, group_service, task_service, user_group_service)
    with pytest.raises(BadRequestError) as exc_info:
        task_group_service.assign(task.taskId, group.groupId, creator.userId)
    assert exc_info.value.error_code == ErrorCode.TASK_CREATOR_CANNOT_BE_ASSIGNEE
    assert exc_info.value.http_code == 400
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_task_group_service.py::test_assign_raises_bad_request_if_assignee_is_task_creator -v`
Expected: FAIL — today assigning to the creator fails with `ASSIGNEE_NOT_GROUP_MEMBER` (`ERR_TASKS_001`), not the new, more specific code, since the creator (post-Task-2) is never a group member either — the test's assertion on `TASK_CREATOR_CANNOT_BE_ASSIGNEE` won't match.

- [ ] **Step 3: Add the check in `TaskGroupService.assign`**

In `app/services/task_group_service.py`, change:
```python
    def assign(self, task_id: str, group_id: str, assignee_id: str) -> TaskGroupRelationship:
        self._task_service.get_task(task_id)
        self._group_service.get_group(group_id)
        self._user_service.get_user(assignee_id)
        if not self._user_group_service.is_member(assignee_id, group_id):
            raise BadRequestError(ErrorCode.ASSIGNEE_NOT_GROUP_MEMBER)
```
to:
```python
    def assign(self, task_id: str, group_id: str, assignee_id: str) -> TaskGroupRelationship:
        task = self._task_service.get_task(task_id)
        self._group_service.get_group(group_id)
        self._user_service.get_user(assignee_id)
        if assignee_id == task.createdBy:
            raise BadRequestError(ErrorCode.TASK_CREATOR_CANNOT_BE_ASSIGNEE)
        if not self._user_group_service.is_member(assignee_id, group_id):
            raise BadRequestError(ErrorCode.ASSIGNEE_NOT_GROUP_MEMBER)
```
(Captures the previously-discarded return value of `get_task` so `task.createdBy` is available; the new check runs before the membership check so the more specific error wins — same precedent as Task 1.)

- [ ] **Step 4: Run the new test, then the full file**

Run: `.venv/bin/pytest tests/unit/test_task_group_service.py -v`
Expected: PASS — all 10 tests.

- [ ] **Step 5: Add the integration test**

Add to the end of `tests/integration/test_task_group_api.py`:
```python
def test_assign_task_to_creator_returns_400(client):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)
    task_id = _create_task(client, creator_id)

    response = client.post(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": creator_id}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["errorCode"] == "ERR_TASKS_005"
```

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: PASS — every test across `tests/unit`, `tests/integration`, `tests/repositories`.

- [ ] **Step 7: Commit**

```bash
git add app/services/task_group_service.py tests/unit/test_task_group_service.py tests/integration/test_task_group_api.py
git commit -m "feat: forbid assigning a task to its own creator"
```

---

## Task 4: Documentation

**Files:**
- Modify: `OpenPoints.md`
- Modify: `Arch.md`

**Interfaces:**
- Consumes: everything from Tasks 1-3.
- Produces: nothing (terminal task).

- [ ] **Step 1: Update the error code table in `OpenPoints.md`**

Change:
```markdown
| Code | Meaning |
|---|---|
| `ERR_TASKS_001` | Assignee is not a member of the target group |
| `ERR_TASKS_002` | Task is already COMPLETED and cannot be marked COMPLETED again |
| `ERR_TASKS_003` | User is already associated with this group |
```
to:
```markdown
| Code | Meaning |
|---|---|
| `ERR_TASKS_001` | Assignee is not a member of the target group |
| `ERR_TASKS_002` | Task is already in the requested state (any no-op state transition, not just COMPLETED->COMPLETED) |
| `ERR_TASKS_003` | User is already associated with this group |
| `ERR_TASKS_005` | Task creator cannot be assigned to their own task |
| `ERR_TASKS_006` | Group creator cannot be a member of their own group |

Note: `ERR_TASKS_004` is intentionally unused. The original ask called for
a separate "task already in requested state" code, but that was folded
into a broadened `ERR_TASKS_002` instead of introduced as a new,
overlapping code.
```

- [ ] **Step 2: Add the new constraints to `Arch.md`'s Entity relationships section**

Change:
```markdown
## Entity relationships

- `User` 1—0..N `UserGroupRelationship` N—1 `Group` (many-to-many join with
  a `relationship` label, e.g. "Father").
- `Task` 0..1—0..N `TaskGroupRelationship` N—0..1 `Group`, with an optional
  `assigneeId` (a `User`) on each join row.
```
to:
```markdown
## Entity relationships

- `User` 1—0..N `UserGroupRelationship` N—1 `Group` (many-to-many join with
  a `relationship` label, e.g. "Father"). Constraint: a group's creator
  (`Group.groupCreaterId`) can never be one of its own members — enforced
  in `UserGroupService.associate`.
- `Task` 0..1—0..N `TaskGroupRelationship` N—0..1 `Group`, with an optional
  `assigneeId` (a `User`) on each join row. Constraint: a task's creator
  (`Task.createdBy`) can never be its own assignee — enforced in
  `TaskGroupService.assign`.
```

- [ ] **Step 3: Run the full suite once more**

Run: `.venv/bin/pytest -v`
Expected: PASS — documentation-only changes, confirms nothing regressed.

- [ ] **Step 4: Commit**

```bash
git add OpenPoints.md Arch.md
git commit -m "docs: document the new task/group validation rules and error codes"
```

---

## Self-Review

**Spec coverage:** `ASK.md`'s three fixes map directly to Tasks 1 (state), 3 (task assignee), 2 (group membership) — reordered so Task 2's fixture fixes land before Task 3 relies on them. `ERR_TASKS_004`'s omission was explicitly resolved with the user and is documented rather than silently skipped.

**Placeholder scan:** every step has literal code, exact diffs, or an exact command with expected output.

**Type consistency:** `ErrorCode.TASK_ALREADY_IN_REQUESTED_STATE`, `TASK_CREATOR_CANNOT_BE_ASSIGNEE`, `GROUP_CREATOR_CANNOT_BE_MEMBER` are spelled identically everywhere they're defined (Task 1) and asserted against (Tasks 1-3's tests). `_setup`'s return tuple `(creator, assignee, group, task)` is unchanged in shape, so every existing caller in `test_task_group_service.py` keeps working without unpacking changes.
