# Group-creator-as-SELF-member, creator-only associate/disassociate, remove assign endpoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement ASK.md's 3 asks: auto-associate a group's creator as a `SELF` member at creation time (removing the rule that blocked it); restrict `associate`/`disassociate` to creator-only and forbid disassociating the creator (`ERR_TASKS_009`); remove the `POST /api/v1/groups/{group_id}/tasks/{task_id}/assignee` endpoint and the now-redundant creator-exemption inside `reassign()`.

**Architecture:** Small, surgical changes to `GroupService`, `UserGroupService`, `TaskGroupService`, and two routers. No schema/migration changes needed (`UserGroupRelationship.relationship` is already a plain string, `"SELF"` is just a value). `GroupService` cannot depend on `UserGroupService` (circular import — `UserGroupService` already depends on `GroupService`), so the auto-association inserts directly via the already-injected `UserGroupRepository`.

**Tech Stack:** FastAPI, SQLAlchemy + psycopg3, Pydantic, pytest against real Postgres (`tasks_net_db_test`).

## Global Constraints

- Python 3.13, existing `.venv` — no new dependencies, no migration needed.
- `ERR_TASKS_004`, `ERR_TASKS_005`, and (after this plan) `ERR_TASKS_006` are intentionally-skipped gaps in the error code numbering — never reuse any of them. `ERR_TASKS_009` is the next free number.
- Command reference: `.venv/bin/pytest -v` (full suite), `.venv/bin/pytest tests/unit/test_user_group_service.py -v` (single file).

---

## Task 1: Exceptions — retire ERR_TASKS_006, add ERR_TASKS_009

**Files:**
- Modify: `app/exceptions.py`

**Interfaces:**
- Produces: `ErrorCode.GROUP_CREATOR_CANNOT_BE_DEASSOCIATED = "ERR_TASKS_009"` — consumed by Task 4 (`UserGroupService.disassociate`).
- Removes: `ErrorCode.GROUP_CREATOR_CANNOT_BE_MEMBER` — its last usage is removed in Task 3.

- [ ] **Step 1: Edit `app/exceptions.py`**

Replace the `ErrorCode` class and `ERROR_CODE_MESSAGES` dict with:

```python
class ErrorCode:
    ASSIGNEE_NOT_GROUP_MEMBER = "ERR_TASKS_001"
    TASK_ALREADY_IN_REQUESTED_STATE = "ERR_TASKS_002"
    DUPLICATE_GROUP_MEMBERSHIP = "ERR_TASKS_003"
    REASSIGN_ASSIGNEE_UNCHANGED = "ERR_TASKS_007"
    REASSIGN_ASSIGNEE_NOT_GROUP_MEMBER = "ERR_TASKS_008"
    GROUP_CREATOR_CANNOT_BE_DEASSOCIATED = "ERR_TASKS_009"


ERROR_CODE_MESSAGES: dict[str, str] = {
    ErrorCode.ASSIGNEE_NOT_GROUP_MEMBER: "Assignee is not a member of the target group",
    ErrorCode.TASK_ALREADY_IN_REQUESTED_STATE: "Task is already in the requested state",
    ErrorCode.DUPLICATE_GROUP_MEMBERSHIP: "User is already associated with this group",
    ErrorCode.REASSIGN_ASSIGNEE_UNCHANGED: "Requested Task assignee is same as current assignee",
    ErrorCode.REASSIGN_ASSIGNEE_NOT_GROUP_MEMBER: "Requested Assignee is not part of the Group",
    ErrorCode.GROUP_CREATOR_CANNOT_BE_DEASSOCIATED: "Group creator cannot be de-associated with group",
}
```

(Everything else in the file — `NotFoundError`, `ForbiddenError`, `ConflictError`, `BadRequestError` — is unchanged.)

This temporarily breaks `tests/unit/test_user_group_service.py::test_associate_raises_bad_request_if_user_is_group_creator` and `tests/integration/test_groups_api.py`/`test_user_group_api.py::test_associate_group_creator_returns_400` (both reference `ErrorCode.GROUP_CREATOR_CANNOT_BE_MEMBER`/`"ERR_TASKS_006"`) — expected, fixed in Task 3. Don't run the full suite yet.

- [ ] **Step 2: Commit**

```bash
git add app/exceptions.py
git commit -m "feat: retire ERR_TASKS_006, add ERR_TASKS_009 for creator de-association"
```

---

## Task 2: `GroupService.create_group` — auto-associate creator as SELF member

**Files:**
- Modify: `app/services/group_service.py`
- Modify: `tests/unit/test_group_service.py`

**Interfaces:**
- Consumes: `UserGroupRepository.add` (existing, already injected as `self._user_group_repository`), `UserGroupRelationship` (existing model, `app/models/user_group.py`).
- Produces: every `Group` created via `GroupService.create_group` now has a matching `UserGroupRelationship(relationship="SELF")` row for its creator — consumed implicitly by Task 3/4's authorization logic and by every test that now expects the creator to show up in a group's member list.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_group_service.py` (`UserGroupRepository` is already imported at the top of this file; `db_session` is a fixture every test here can request directly — the same session `group_service` was built from):

```python
def test_create_group_auto_associates_creator_as_self_member(
    group_service: GroupService, user_service: UserService, db_session
):
    creator = user_service.create_user(user_id="ada", first_name="Ada", last_name="Lovelace")
    group = group_service.create_group(
        group_name="Smiths", group_desc=None, group_category="Family", creater_id=creator.userId
    )

    relationship = UserGroupRepository(db_session).find_by_user_and_group(creator.userId, group.groupId)
    assert relationship is not None
    assert relationship.relationship == "SELF"
```

Place this test right after `test_create_group_succeeds_for_existing_creator`.

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest tests/unit/test_group_service.py::test_create_group_auto_associates_creator_as_self_member -v
```
Expected: FAIL — `assert relationship is not None` fails (`relationship` is `None` since no membership row is created today).

- [ ] **Step 3: Implement — edit `app/services/group_service.py`**

Add an import and one block inside `create_group`:

```python
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.exceptions import ForbiddenError, NotFoundError
from app.models.enums import GroupStatus
from app.models.group import Group
from app.models.user_group import UserGroupRelationship
from app.repositories.group_repository import GroupRepository
from app.repositories.user_group_repository import UserGroupRepository
from app.services.user_service import UserService


class GroupService:
    def __init__(
        self,
        repository: GroupRepository,
        user_service: UserService,
        user_group_repository: UserGroupRepository,
    ):
        self._repository = repository
        self._user_service = user_service
        self._user_group_repository = user_group_repository

    def create_group(
        self,
        group_name: str,
        group_desc: Optional[str],
        group_category: str,
        creater_id: str,
        group_icon_url: Optional[str] = None,
    ) -> Group:
        self._user_service.get_user(creater_id)
        now = datetime.now(timezone.utc)
        group = Group(
            groupId=str(uuid.uuid4()),
            groupName=group_name,
            groupDesc=group_desc,
            groupCategory=group_category,
            groupStatus=GroupStatus.ACTIVE,
            groupIconUrl=group_icon_url,
            groupCreaterId=creater_id,
            createdAt=now,
            updatedAt=None,
        )
        created = self._repository.add(group)
        # Every group's creator is automatically a SELF member. Inserted
        # directly (bypassing UserGroupService.associate()) because
        # GroupService cannot depend on UserGroupService — that would be a
        # circular import (UserGroupService already depends on GroupService).
        self._user_group_repository.add(
            UserGroupRelationship(
                uuid=str(uuid.uuid4()),
                groupId=created.groupId,
                userId=creater_id,
                relationship="SELF",
            )
        )
        return created
```

(Only `create_group` changes — `get_group`, `get_groups_by_creator`, `update_group`, `set_status` are untouched.)

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/pytest tests/unit/test_group_service.py -v
```
Expected: all PASS, including the new test. (Other files may now show failures from the ripple — that's expected, fixed in later tasks. Don't run the full suite yet.)

- [ ] **Step 5: Commit**

```bash
git add app/services/group_service.py tests/unit/test_group_service.py
git commit -m "feat: auto-associate a group's creator as a SELF member at creation"
```

---

## Task 3: `UserGroupService.associate` — remove creator-block, restrict to creator-only

**Files:**
- Modify: `app/services/user_group_service.py`
- Modify: `tests/unit/test_user_group_service.py`

**Interfaces:**
- Produces: `associate(user_id, group_id, relationship, current_user_id=None)` — same signature, new authorization (creator-only instead of creator-or-member) and the creator-cannot-be-member rule removed entirely.

- [ ] **Step 1: Update the tests**

In `tests/unit/test_user_group_service.py`:

Delete `test_associate_raises_bad_request_if_user_is_group_creator` entirely (contradicts the new behavior — the creator is now already a member from creation, so associating them again hits `DUPLICATE_GROUP_MEMBERSHIP` instead, covered separately below).

Rename `test_associate_raises_forbidden_if_caller_is_not_creator_or_member` to `test_associate_raises_forbidden_if_caller_is_not_creator` (body unchanged — an "outsider" caller is still forbidden either way):

```python
def test_associate_raises_forbidden_if_caller_is_not_creator(
    user_group_service: UserGroupService, group_service, user_service
):
    _, group = _make_user_and_group(user_service, group_service)
    member = user_service.create_user(user_id="bob", first_name="Bob", last_name="Smith")
    with pytest.raises(ForbiddenError):
        user_group_service.associate(member.userId, group.groupId, "Father", current_user_id="outsider")
```

Add a new test proving a plain (non-creator) member can no longer associate others (this is the actual new restriction — previously any member could):

```python
def test_associate_raises_forbidden_if_caller_is_a_member_not_creator(
    user_group_service: UserGroupService, group_service, user_service
):
    creator, group = _make_user_and_group(user_service, group_service)
    member = user_service.create_user(user_id="bob", first_name="Bob", last_name="Smith")
    user_group_service.associate(member.userId, group.groupId, "Father")
    outsider = user_service.create_user(user_id="cara", first_name="Cara", last_name="Jones")

    with pytest.raises(ForbiddenError):
        user_group_service.associate(
            outsider.userId, group.groupId, "Cousin", current_user_id=member.userId
        )
```

Add a test confirming the creator CAN still associate others:

```python
def test_associate_succeeds_for_creator_caller(
    user_group_service: UserGroupService, group_service, user_service
):
    creator, group = _make_user_and_group(user_service, group_service)
    member = user_service.create_user(user_id="bob", first_name="Bob", last_name="Smith")

    relationship = user_group_service.associate(
        member.userId, group.groupId, "Father", current_user_id=creator.userId
    )
    assert relationship.userId == member.userId
```

Add a test confirming the creator-block removal — associating the creator now hits `DUPLICATE_GROUP_MEMBERSHIP` (since they're already a `SELF` member from creation), not the old `GROUP_CREATOR_CANNOT_BE_MEMBER`:

```python
def test_associate_creator_again_raises_duplicate_membership(
    user_group_service: UserGroupService, group_service, user_service
):
    creator, group = _make_user_and_group(user_service, group_service)
    with pytest.raises(BadRequestError) as exc_info:
        user_group_service.associate(creator.userId, group.groupId, "Father")
    assert exc_info.value.error_code == ErrorCode.DUPLICATE_GROUP_MEMBERSHIP
```

Fix the member-count ripple from Task 2 (creator now always shows up in `list_by_group`) in `test_list_by_group_returns_members`:

```python
def test_list_by_group_returns_members(user_group_service: UserGroupService, group_service, user_service):
    creator, group = _make_user_and_group(user_service, group_service)
    member = user_service.create_user(user_id="bob", first_name="Bob", last_name="Smith")
    user_group_service.associate(member.userId, group.groupId, "Father")

    members = user_group_service.list_by_group(group.groupId)

    assert len(members) == 2
    member_ids = {m.userId for m in members}
    assert member_ids == {creator.userId, member.userId}
    self_entry = next(m for m in members if m.userId == creator.userId)
    assert self_entry.relationship == "SELF"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/unit/test_user_group_service.py -v
```
Expected: `test_associate_raises_forbidden_if_caller_is_a_member_not_creator` FAILs (member currently CAN associate, so no `ForbiddenError` is raised); `test_associate_creator_again_raises_duplicate_membership` FAILs (`ErrorCode.GROUP_CREATOR_CANNOT_BE_MEMBER` — wait, this constant no longer exists after Task 1, so this old check path is unreachable — actually the CURRENT code still has the `if user_id == group.groupCreaterId` check referencing the now-deleted `ErrorCode.GROUP_CREATOR_CANNOT_BE_MEMBER`, so this will raise `AttributeError: type object 'ErrorCode' has no attribute 'GROUP_CREATOR_CANNOT_BE_MEMBER'` until Step 3 removes that line); `test_list_by_group_returns_members` FAILs (`len(members) == 2` assertion fails since only 1 member exists today — the creator isn't associated in the current `_make_user_and_group` + `group_service.create_group` path, or rather it now IS thanks to Task 2, so this one should actually already reflect 2 — double check by running, this is testing whether Task 2's effect is visible here, and it should already pass if Task 2 landed correctly, but the *old* test asserted `len == 1` — with the rename this is a genuinely new assertion, so it's the AttributeError above that blocks collection of the whole file first).

- [ ] **Step 3: Implement — edit `app/services/user_group_service.py`**

Replace `associate`:

```python
    def associate(
        self, user_id: str, group_id: str, relationship: str, current_user_id: Optional[str] = None
    ) -> UserGroupRelationship:
        self._user_service.get_user(user_id)
        group = self._group_service.get_group(group_id)
        if current_user_id is not None and current_user_id != group.groupCreaterId:
            raise ForbiddenError(
                f"User {current_user_id} is not authorized to associate users with group {group_id}"
            )
        if self.is_member(user_id, group_id):
            raise BadRequestError(ErrorCode.DUPLICATE_GROUP_MEMBERSHIP)
        entity = UserGroupRelationship(
            uuid=str(uuid.uuid4()), groupId=group_id, userId=user_id, relationship=relationship
        )
        return self._repository.add(entity)
```

(The `if user_id == group.groupCreaterId: raise BadRequestError(ErrorCode.GROUP_CREATOR_CANNOT_BE_MEMBER)` block is deleted; `group = self._group_service.get_group(group_id, current_user_id=current_user_id)` becomes `group = self._group_service.get_group(group_id)` — existence-only, no more creator-or-member delegation — followed by the new explicit creator-only check.)

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/unit/test_user_group_service.py -v
```
Expected: all currently-collectible tests PASS. (`test_disassociate_*` tests may still fail — that's Task 4's job, not this one. If any `disassociate` test errors out and blocks collection of the whole file, temporarily skip ahead to confirm only `associate`-related tests pass, then proceed to Task 4 immediately.)

- [ ] **Step 5: Commit**

```bash
git add app/services/user_group_service.py tests/unit/test_user_group_service.py
git commit -m "feat: restrict UserGroupService.associate to creator-only, drop creator-cannot-be-member rule"
```

---

## Task 4: `UserGroupService.disassociate` — creator-only, creator cannot be de-associated

**Files:**
- Modify: `app/services/user_group_service.py`
- Modify: `app/api/v1/user_group.py`
- Modify: `tests/unit/test_user_group_service.py`

**Interfaces:**
- Consumes: `ErrorCode.GROUP_CREATOR_CANNOT_BE_DEASSOCIATED` (Task 1).
- Produces: `disassociate(user_id, group_id, current_user_id=None)` — same signature, new authorization (creator-only, no more self-removal for non-creators) and new rule (creator can never be the target).

- [ ] **Step 1: Update the tests**

In `tests/unit/test_user_group_service.py`:

Replace `test_disassociate_removes_relationship` (previously asserted `list_by_group == []` after disassociating the only non-creator member — now the creator's `SELF` row remains):

```python
def test_disassociate_removes_relationship(user_group_service: UserGroupService, group_service, user_service):
    creator, group = _make_user_and_group(user_service, group_service)
    member = user_service.create_user(user_id="bob", first_name="Bob", last_name="Smith")
    user_group_service.associate(member.userId, group.groupId, "Father", current_user_id=creator.userId)
    user_group_service.disassociate(member.userId, group.groupId, current_user_id=creator.userId)

    members = user_group_service.list_by_group(group.groupId)
    assert [m.userId for m in members] == [creator.userId]
```

Replace `test_disassociate_succeeds_for_creator_removing_someone_else` similarly (same fix, `list_by_group` no longer empty):

```python
def test_disassociate_succeeds_for_creator_removing_someone_else(
    user_group_service: UserGroupService, group_service, user_service
):
    creator, group = _make_user_and_group(user_service, group_service)
    member = user_service.create_user(user_id="bob", first_name="Bob", last_name="Smith")
    user_group_service.associate(member.userId, group.groupId, "Father", current_user_id=creator.userId)
    user_group_service.disassociate(member.userId, group.groupId, current_user_id=creator.userId)
    members = user_group_service.list_by_group(group.groupId)
    assert [m.userId for m in members] == [creator.userId]
```

Delete `test_disassociate_raises_forbidden_if_caller_is_neither_member_nor_creator` and replace with a version proving a plain member (not just a true outsider) is ALSO now forbidden from disassociating someone else — and add the "member cannot self-disassociate" and "creator cannot be de-associated" cases:

```python
def test_disassociate_raises_forbidden_if_caller_is_not_creator(
    user_group_service: UserGroupService, group_service, user_service
):
    creator, group = _make_user_and_group(user_service, group_service)
    member = user_service.create_user(user_id="bob", first_name="Bob", last_name="Smith")
    user_group_service.associate(member.userId, group.groupId, "Father", current_user_id=creator.userId)
    with pytest.raises(ForbiddenError):
        user_group_service.disassociate(member.userId, group.groupId, current_user_id="outsider")


def test_disassociate_raises_forbidden_if_member_tries_to_self_disassociate(
    user_group_service: UserGroupService, group_service, user_service
):
    creator, group = _make_user_and_group(user_service, group_service)
    member = user_service.create_user(user_id="bob", first_name="Bob", last_name="Smith")
    user_group_service.associate(member.userId, group.groupId, "Father", current_user_id=creator.userId)
    with pytest.raises(ForbiddenError):
        user_group_service.disassociate(member.userId, group.groupId, current_user_id=member.userId)


def test_disassociate_raises_bad_request_if_target_is_creator(
    user_group_service: UserGroupService, group_service, user_service
):
    creator, group = _make_user_and_group(user_service, group_service)
    with pytest.raises(BadRequestError) as exc_info:
        user_group_service.disassociate(creator.userId, group.groupId, current_user_id=creator.userId)
    assert exc_info.value.error_code == ErrorCode.GROUP_CREATOR_CANNOT_BE_DEASSOCIATED
    assert exc_info.value.http_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/unit/test_user_group_service.py -v
```
Expected: `test_disassociate_raises_forbidden_if_member_tries_to_self_disassociate` FAILs (today self-removal always succeeds, no `ForbiddenError`); `test_disassociate_raises_bad_request_if_target_is_creator` FAILs (nothing today stops the creator from being disassociated — either succeeds silently or raises `NotFoundError` depending on whether they were already a member; expect it does NOT raise `BadRequestError`).

- [ ] **Step 3: Implement — edit `app/services/user_group_service.py`**

Replace `disassociate`:

```python
    def disassociate(self, user_id: str, group_id: str, current_user_id: Optional[str] = None) -> None:
        group = self._group_service.get_group(group_id)
        if current_user_id is not None and current_user_id != group.groupCreaterId:
            raise ForbiddenError(
                f"User {current_user_id} is not authorized to remove user {user_id} from group {group_id}"
            )
        if user_id == group.groupCreaterId:
            raise BadRequestError(ErrorCode.GROUP_CREATOR_CANNOT_BE_DEASSOCIATED)
        existing = self._repository.find_by_user_and_group(user_id, group_id)
        if existing is None:
            raise NotFoundError(f"User {user_id} is not associated with group {group_id}")
        self._repository.delete(existing.uuid)
```

(Previously the group was only fetched inside the `if current_user_id != user_id` branch; now it's fetched unconditionally, since the creator-only authorization check and the creator-cannot-be-deassociated check both need `group.groupCreaterId` regardless of who's calling.)

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/unit/test_user_group_service.py -v
```
Expected: all PASS.

- [ ] **Step 5: Add `BadRequestError` handling to the router — edit `app/api/v1/user_group.py`**

`disassociate_user` currently has no `BadRequestError` handler (only `NotFoundError`/`ForbiddenError`). Add one, mirroring `associate_user`'s existing pattern:

```python
@router.delete(
    "/{group_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        404: {"description": "User is not associated with this group"},
        400: {"model": BadRequestResponse, "description": "Group creator cannot be de-associated"},
        403: {"description": "Not authorized"},
    },
)
def disassociate_user(
    group_id: str,
    user_id: str,
    current_user_id: str = Depends(verify_firebase_token),
    service: UserGroupService = Depends(get_user_group_service),
) -> None:
    try:
        service.disassociate(user_id, group_id, current_user_id=current_user_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BadRequestError as exc:
        raise HTTPException(
            status_code=exc.http_code,
            detail=ErrorDetail(errorCode=exc.error_code, message=exc.message).model_dump(),
        ) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
```

(`BadRequestError` and `BadRequestResponse`/`ErrorDetail` are already imported at the top of this file — no new imports needed.)

- [ ] **Step 6: Commit**

```bash
git add app/services/user_group_service.py app/api/v1/user_group.py tests/unit/test_user_group_service.py
git commit -m "feat: restrict UserGroupService.disassociate to creator-only, add ERR_TASKS_009"
```

---

## Task 5: `TaskGroupService.reassign` — drop the now-redundant creator exemption

**Files:**
- Modify: `app/services/task_group_service.py`

**Interfaces:**
- No signature change. Behavior: since Task 2 makes every group's creator a real `UserGroupRelationship` member, `is_member(task.createdBy, group_id)` is now `True` whenever the task's creator also created (or is a member of) that group — the exemption is redundant for that case and this removes it.

- [ ] **Step 1: Verify no test regresses first (no test changes needed)**

Before touching the code, confirm by inspection that every existing `reassign` test in `tests/unit/test_task_group_service.py` and `tests/integration/test_task_group_api.py` that reassigns **to** the creator (`test_reassign_succeeds_for_creator_caller`, `test_reassign_succeeds_for_plain_member_caller` — both reassign to `creator.userId`) will keep passing once the creator is a real member (Task 2's effect) — they will, since `is_member(creator.userId, group.groupId)` becomes `True` on its own merits now, independent of any exemption. No test file changes are required for this task.

- [ ] **Step 2: Run the current reassign tests to establish a passing baseline**

```bash
.venv/bin/pytest tests/unit/test_task_group_service.py -k reassign -v
.venv/bin/pytest tests/integration/test_task_group_api.py -k reassign -v
```
Expected: all PASS (baseline, before the code change).

- [ ] **Step 3: Implement — edit `app/services/task_group_service.py`**

In `reassign`, change:
```python
        if assignee_id != task.createdBy and not self._user_group_service.is_member(assignee_id, group_id):
            raise BadRequestError(ErrorCode.REASSIGN_ASSIGNEE_NOT_GROUP_MEMBER)
```
to:
```python
        if not self._user_group_service.is_member(assignee_id, group_id):
            raise BadRequestError(ErrorCode.REASSIGN_ASSIGNEE_NOT_GROUP_MEMBER)
```
(`task` is still used earlier in the method for the `existing`/`NotFoundError` flow — no other line references `task.createdBy` in `reassign`, so nothing else changes. `assign()`'s equivalent line is untouched — ask 3 only mentions `reassign()`.)

- [ ] **Step 4: Run tests to verify they still pass**

```bash
.venv/bin/pytest tests/unit/test_task_group_service.py -k reassign -v
.venv/bin/pytest tests/integration/test_task_group_api.py -k reassign -v
```
Expected: all PASS, unchanged from Step 2's baseline (confirms the exemption really was redundant).

- [ ] **Step 5: Commit**

```bash
git add app/services/task_group_service.py
git commit -m "feat: drop redundant creator exemption in TaskGroupService.reassign"
```

---

## Task 6: Remove the `POST /api/v1/groups/{group_id}/tasks/{task_id}/assignee` (assign) endpoint

**Files:**
- Modify: `app/api/v1/task_group.py`
- Modify: `tests/integration/test_task_group_api.py`
- Modify: `tests/integration/test_full_lifecycle_api.py`

**Interfaces:**
- Removes the `assign_task` route only. `TaskGroupService.assign()` (the service method) is NOT deleted — it's still called directly by unit tests (`tests/unit/test_task_group_service.py`, `tests/unit/test_task_service.py`) as fixture setup, and nothing in production calls it anymore, which is fine (dead-from-HTTP but still a valid internal API).
- Produces: a `_seed_assignment(db_session, task_id, group_id, assignee_id)` test helper in `tests/integration/test_task_group_api.py`, used by every test that previously seeded via `POST .../assignee` and now needs another way to create the initial `TaskGroupRelationship` row before exercising `PATCH .../assignee` (reassign).

- [ ] **Step 1: Update the tests**

In `tests/integration/test_task_group_api.py`, delete these five tests entirely (they test the removed route): `test_assign_task_to_group_member`, `test_assign_task_wrong_caller_returns_403`, `test_assign_task_unknown_assignee_returns_404`, `test_assign_task_to_non_member_returns_400`, `test_assign_task_to_creator_now_succeeds`.

Add a helper near the top of the file (after the existing `_associate_user` helper):

```python
def _seed_assignment(db_session, task_id, group_id, assignee_id):
    import uuid

    from app.models.task_group import TaskGroupRelationship
    from app.repositories.task_group_repository import TaskGroupRepository

    TaskGroupRepository(db_session).add(
        TaskGroupRelationship(uuid=str(uuid.uuid4()), taskId=task_id, groupId=group_id, assigneeId=assignee_id)
    )
```

Add a new test confirming the route is gone:

```python
def test_assign_route_removed_returns_404(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    group_id = _create_group(client, authenticate_as, creator_id)
    task_id = _create_task(client, authenticate_as, creator_id)
    response = client.post(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": creator_id}
    )
    assert response.status_code == 404
```

For every remaining test that used `client.post(f".../assignee", json={"assigneeId": ...})` as setup, replace that call with `_seed_assignment(db_session, task_id, group_id, ...)` and add `db_session` as a test parameter (it's already available — `client` itself depends on it, so requesting both in the same test gives you the same session/transaction). Apply this to:

```python
def test_reassign_task_to_new_member_succeeds(client, authenticate_as, db_session):
    creator_id = _create_user(client, authenticate_as, "creator")
    member_id = _create_user(client, authenticate_as, "member", first_name="Bob", last_name="Smith")
    other_member_id = _create_user(client, authenticate_as, "other", first_name="Cara", last_name="Jones")
    group_id = _create_group(client, authenticate_as, creator_id)
    task_id = _create_task(client, authenticate_as, creator_id)
    _associate_user(client, group_id, member_id)
    _associate_user(client, group_id, other_member_id)
    _seed_assignment(db_session, task_id, group_id, member_id)

    response = client.patch(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": other_member_id}
    )
    assert response.status_code == 200
    assert response.json()["assigneeId"] == other_member_id


def test_reassign_task_same_assignee_returns_400_err_007(client, authenticate_as, db_session):
    creator_id = _create_user(client, authenticate_as, "creator")
    member_id = _create_user(client, authenticate_as, "member", first_name="Bob", last_name="Smith")
    group_id = _create_group(client, authenticate_as, creator_id)
    task_id = _create_task(client, authenticate_as, creator_id)
    _associate_user(client, group_id, member_id)
    _seed_assignment(db_session, task_id, group_id, member_id)

    response = client.patch(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": member_id}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["errorCode"] == "ERR_TASKS_007"


def test_reassign_task_non_member_returns_400_err_008(client, authenticate_as, db_session):
    creator_id = _create_user(client, authenticate_as, "creator")
    member_id = _create_user(client, authenticate_as, "member", first_name="Bob", last_name="Smith")
    outsider_id = _create_user(client, authenticate_as, "outsider", first_name="Cara", last_name="Jones")
    group_id = _create_group(client, authenticate_as, creator_id)
    task_id = _create_task(client, authenticate_as, creator_id)
    _associate_user(client, group_id, member_id)
    _seed_assignment(db_session, task_id, group_id, member_id)

    response = client.patch(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": outsider_id}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["errorCode"] == "ERR_TASKS_008"


def test_reassign_task_any_member_can_call_not_just_creator(client, authenticate_as, db_session):
    creator_id = _create_user(client, authenticate_as, "creator")
    member_id = _create_user(client, authenticate_as, "member", first_name="Bob", last_name="Smith")
    group_id = _create_group(client, authenticate_as, creator_id)
    task_id = _create_task(client, authenticate_as, creator_id)
    _associate_user(client, group_id, member_id)
    _seed_assignment(db_session, task_id, group_id, member_id)

    authenticate_as(member_id)
    response = client.patch(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": creator_id}
    )
    assert response.status_code == 200
    assert response.json()["assigneeId"] == creator_id


def test_reassign_task_non_member_caller_returns_403(client, authenticate_as, db_session):
    creator_id = _create_user(client, authenticate_as, "creator")
    member_id = _create_user(client, authenticate_as, "member", first_name="Bob", last_name="Smith")
    group_id = _create_group(client, authenticate_as, creator_id)
    task_id = _create_task(client, authenticate_as, creator_id)
    _associate_user(client, group_id, member_id)
    _seed_assignment(db_session, task_id, group_id, member_id)

    authenticate_as("outsider")
    response = client.patch(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": creator_id}
    )
    assert response.status_code == 403
```

`test_list_group_tasks_as_creator`, `test_list_group_tasks_as_member`, `test_list_group_tasks_non_member_returns_403`, `test_list_group_tasks_unknown_group_returns_404` don't call the assign route at all (they create tasks with `groupId` set directly, which auto-assigns per the earlier `groupId` feature) — leave them unchanged.

In `tests/integration/test_full_lifecycle_api.py`, replace step 6 (which currently does `client.post(f".../assignee", json=...)`) with a direct seed:

```python
    # 6. Seed the task's assignment to the member within the group directly
    #    (the POST .../assignee endpoint was removed — assignment now only
    #    happens via auto-assign-on-create-with-groupId, or via PATCH reassign
    #    once an assignment already exists).
    import uuid

    from app.models.task_group import TaskGroupRelationship
    from app.repositories.task_group_repository import TaskGroupRepository

    TaskGroupRepository(db_session).add(
        TaskGroupRelationship(uuid=str(uuid.uuid4()), taskId=task_id, groupId=group_id, assigneeId=member_id)
    )
```

and change the test function signature to `def test_full_cross_entity_lifecycle(client, authenticate_as, db_session):` (add `db_session`). Delete the now-unused assertions that referenced `assign_response` (the four lines checking `assign_response.status_code == 201` and its body fields) since there's no HTTP response to check anymore.

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/integration/test_task_group_api.py tests/integration/test_full_lifecycle_api.py -v
```
Expected: `test_assign_route_removed_returns_404` FAILs (route still exists, returns 201 not 404); the five deleted-and-no-longer-collected assign tests are gone from output; the rewritten reassign tests should still PASS already (since `_seed_assignment` works today regardless of whether the route is removed) — this confirms the seeding rewrite itself is correct before removing the route.

- [ ] **Step 3: Implement — edit `app/api/v1/task_group.py`**

Delete the entire `assign_task` function and its `@router.post("", ...)` decorator (lines defining it, roughly lines 16-49 of the current file) — from the `@router.post(` decorator through the `return TaskGroupResponse(**relationship.model_dump())` line that ends `assign_task`. Everything else in the file (`router` object itself, `reassign_task`, `group_tasks_router`, `list_group_tasks`) stays exactly as-is. No import changes needed (all remaining code still uses the same imports).

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/integration/test_task_group_api.py tests/integration/test_full_lifecycle_api.py -v
```
Expected: all PASS, including `test_assign_route_removed_returns_404` (now genuinely 404 — no route matches `POST` at that path anymore, and no other method is registered at that exact sub-path besides `PATCH`/existing `router`, so FastAPI returns 404 not 405 — consistent with the existing `test_delete_assignee_route_removed_returns_404` precedent in the same file).

- [ ] **Step 5: Commit**

```bash
git add app/api/v1/task_group.py tests/integration/test_task_group_api.py tests/integration/test_full_lifecycle_api.py
git commit -m "feat: remove POST /assignee (assign) endpoint, seed task-group tests directly"
```

---

## Task 7: Integration test ripple in `test_groups_api.py` / `test_user_group_api.py`

**Files:**
- Modify: `tests/integration/test_user_group_api.py`

**Interfaces:** none (test-only).

- [ ] **Step 1: Update the tests**

`tests/integration/test_groups_api.py` needs **no changes** — it never asserts on member counts or calls associate/disassociate.

In `tests/integration/test_user_group_api.py`:

Replace `test_associate_group_creator_returns_400` (associating the creator again now hits `DUPLICATE_GROUP_MEMBERSHIP`/`ERR_TASKS_003`, not the removed `ERR_TASKS_006`):

```python
def test_associate_group_creator_again_returns_400_duplicate(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    group_id = _create_group(client, authenticate_as, creator_id)

    response = client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": creator_id, "relationship": "Father"}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["errorCode"] == "ERR_TASKS_003"
```

Replace `test_disassociate_self_succeeds` (a non-creator member can no longer self-disassociate — only the creator can disassociate anyone):

```python
def test_disassociate_self_by_non_creator_returns_403(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    member_id = _create_user(client, authenticate_as, "member", first_name="Bob", last_name="Smith")
    group_id = _create_group(client, authenticate_as, creator_id)
    client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": member_id, "relationship": "Father"}
    )

    authenticate_as(member_id)
    response = client.delete(f"/api/v1/groups/{group_id}/members/{member_id}")
    assert response.status_code == 403
```

Replace `test_disassociate_unknown_association_returns_404` (it targeted the creator, which now hits the new creator-cannot-be-deassociated rule instead of "not found" — split into two tests, one keeping real 404 coverage with a genuinely-unassociated other user, one covering the new rule):

```python
def test_disassociate_unassociated_user_returns_404(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    member_id = _create_user(client, authenticate_as, "member", first_name="Bob", last_name="Smith")
    group_id = _create_group(client, authenticate_as, creator_id)

    response = client.delete(f"/api/v1/groups/{group_id}/members/{member_id}")
    assert response.status_code == 404


def test_disassociate_creator_returns_400(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    group_id = _create_group(client, authenticate_as, creator_id)

    response = client.delete(f"/api/v1/groups/{group_id}/members/{creator_id}")
    assert response.status_code == 400
    assert response.json()["detail"]["errorCode"] == "ERR_TASKS_009"
```

Fix the member-count ripple in `test_get_group_members_returns_associated_users`:

```python
def test_get_group_members_returns_associated_users(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    member_id = _create_user(client, authenticate_as, "member", first_name="Bob", last_name="Smith")
    group_id = _create_group(client, authenticate_as, creator_id)
    client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": member_id, "relationship": "Father"}
    )

    response = client.get(f"/api/v1/groups/{group_id}/members")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    by_user = {m["userId"]: m for m in body}
    assert by_user[member_id]["relationship"] == "Father"
    assert by_user[creator_id]["relationship"] == "SELF"
```

Rename and fix `test_get_group_members_empty_list_for_group_with_no_members` (no longer empty — the creator is always there):

```python
def test_get_group_members_returns_only_creator_for_group_with_no_other_members(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    group_id = _create_group(client, authenticate_as, creator_id)

    response = client.get(f"/api/v1/groups/{group_id}/members")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["userId"] == creator_id
    assert body[0]["relationship"] == "SELF"
```

`test_associate_user_to_group`, `test_associate_non_member_non_creator_returns_403`, `test_associate_duplicate_returns_400`, `test_associate_unknown_user_returns_404`, `test_disassociate_user_from_group`, `test_disassociate_wrong_user_returns_403`, `test_get_group_members_non_member_returns_403`, `test_get_group_members_unknown_group_returns_404` are all unaffected by this change and stay exactly as-is (verified by inspection in the plan's research phase).

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/integration/test_user_group_api.py -v
```
Expected: `test_disassociate_self_by_non_creator_returns_403` FAILs (currently 204, not 403); `test_disassociate_creator_returns_400` FAILs (currently the delete either 404s or silently succeeds, not a `400`/`ERR_TASKS_009`); `test_get_group_members_returns_associated_users` FAILs (`len(body) == 2` vs actual `1`); `test_get_group_members_returns_only_creator_for_group_with_no_other_members` FAILs (`len(body) == 1` vs actual `0`); `test_associate_group_creator_again_returns_400_duplicate` should already PASS if Tasks 1-3 landed correctly (confirms no regression, not a new failure).

- [ ] **Step 3: No production code changes needed here** — this task is purely test alignment; Tasks 1-6 already implemented the behavior.

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/integration/test_user_group_api.py tests/integration/test_groups_api.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_user_group_api.py
git commit -m "test: align user-group integration tests with creator-only associate/disassociate and SELF membership"
```

---

## Task 8: Docs — `Arch.md` and `OpenPoints.md`

**Files:**
- Modify: `Arch.md`
- Modify: `OpenPoints.md`

- [ ] **Step 1: Edit `Arch.md`**

In the **Entity relationships** section, update the `User`/`UserGroupRelationship`/`Group` bullet:

```markdown
- `User` 1—0..N `UserGroupRelationship` N—1 `Group` (many-to-many join with
  a `relationship` label, e.g. "Father"). A group's creator is automatically
  associated with `relationship="SELF"` at creation time (inserted directly
  by `GroupService.create_group` via `UserGroupRepository`, bypassing
  `UserGroupService.associate()` to avoid a circular dependency). Only the
  group's creator can associate or disassociate members
  (`UserGroupService.associate`/`disassociate`); the creator themselves can
  never be disassociated.
```

In the **API Endpoint Inventory** table, remove the `POST /api/v1/groups/{groupId}/tasks/{taskId}/assignee` row (the assign endpoint no longer exists — only `PATCH` remains for reassignment).

- [ ] **Step 2: Edit `OpenPoints.md`**

In the **Error codes** table, remove the `ERR_TASKS_006` row, add:
```markdown
| `ERR_TASKS_009` | Group creator cannot be de-associated with group |
```
Update the "intentionally unused" note:
```markdown
Note: `ERR_TASKS_004`, `ERR_TASKS_005`, and `ERR_TASKS_006` are intentionally
unused/retired. `ERR_TASKS_004` was folded into the broadened `ERR_TASKS_002`.
`ERR_TASKS_005` (`TASK_CREATOR_CANNOT_BE_ASSIGNEE`) and `ERR_TASKS_006`
(`GROUP_CREATOR_CANNOT_BE_MEMBER`) were both retired business rules: task
creators can be their own task's assignee, and group creators are now
always members (`relationship="SELF"`) of their own group.
```

In the **Auth & authorization** bullet list, update the group-membership line:
```markdown
  - Group membership: only the group's creator can associate or
    disassociate members (`ForbiddenError`/403 otherwise) — not
    creator-or-member as with other group endpoints. The creator can never
    be disassociated (`BadRequestError`/`ERR_TASKS_009`). Every group
    automatically includes its creator as a `relationship="SELF"` member
    from creation.
  - Tasks: ... Assign: creator only (endpoint removed — assignment now
    only happens via `POST /api/v1/tasks` with a `groupId`, which
    auto-assigns the creator). Reassign: creator or any group member.
```

In the **Design notes / asymmetries** section, add:
```markdown
- `POST /api/v1/groups/{groupId}/tasks/{taskId}/assignee` (manual assign) no
  longer exists. `TaskGroupService.assign()` (the service method) is kept
  because unit tests still use it directly as fixture setup, but nothing in
  production calls it — the only ways a task gets an initial assignment now
  are auto-assign-on-create-with-`groupId`, or (once one exists) `PATCH
  .../assignee` (`reassign`).
```

- [ ] **Step 3: Commit**

```bash
git add Arch.md OpenPoints.md
git commit -m "docs: describe SELF group membership, creator-only associate/disassociate, and removed assign endpoint"
```

---

## Task 9: Full-suite verification

- [ ] **Step 1: Run the full suite**

```bash
.venv/bin/pytest -v
```
Expected: 100% pass. If anything from an earlier task's ripple was missed (e.g. another test elsewhere asserting a group's member count, or calling `associate`/`disassociate` with assumptions that no longer hold), fix it here and commit the fix separately — don't reopen earlier tasks' commits.

- [ ] **Step 2: Manual sanity check (via the integration suite, no live server needed)**

Confirm by re-reading the final state of `tests/integration/test_user_group_api.py` and `tests/integration/test_task_group_api.py` that every scenario from the plan's Context section is covered: creator auto-SELF-membership, creator-only associate/disassociate, creator-cannot-be-deassociated (`ERR_TASKS_009`), and the removed assign route.

- [ ] **Step 3: Final commit (only if fixes were needed in Step 1)**

```bash
git add -A
git commit -m "fix: address issues found during full-suite verification"
```

---

## Self-review notes (per the skill's checklist)

- **Spec coverage**: Ask 1 (SELF-associate creator, remove creator-cannot-be-member) → Tasks 1, 2, 3. Ask 2 (creator-only associate/disassociate, `ERR_TASKS_009`) → Tasks 1, 3, 4. Ask 3 (remove assign endpoint, drop reassign's creator exemption) → Tasks 5, 6. All 3 asks map to at least one task.
- **Type/signature consistency checked**: `associate`/`disassociate`'s signatures are unchanged (`current_user_id: Optional[str] = None` throughout) — only internal authorization logic changes, so no caller (router, other services, tests not touched by this plan) needs a signature-level update. `ErrorCode.GROUP_CREATOR_CANNOT_BE_DEASSOCIATED` (Task 1) matches its usage in Task 4's `disassociate` and Task 7's integration test. `_seed_assignment` (Task 6) is defined once and reused by name consistently across the 5 rewritten reassign tests.
- **Placeholder scan**: no "TBD"/"handle appropriately"-style steps — every step has literal code.
