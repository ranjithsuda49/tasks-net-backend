# Ownership Authorization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add ownership (authorization) checks on top of the existing Firebase authentication, moving `verify_firebase_token` to an explicit `current_user_id` argument everywhere and enforcing the ~15 per-endpoint rules in `ASK.md`, plus a new "my tasks" endpoint.

**Architecture:** Every gated service method gains `current_user_id: Optional[str] = None` — the check only runs when a caller passes a value, so every internal existence-check call site (unaffected, passes nothing) keeps working. `GroupService`/`TaskService` gain a third constructor arg (`UserGroupRepository`/`TaskGroupRepository` respectively — repositories, not sibling services, to avoid circular dependencies) for their "is member"/"is assignee" checks.

**Tech Stack:** Same as the rest of the app — FastAPI, Pydantic, pytest, real PostgreSQL via `db_session`.

## Global Constraints

- 404 (resource doesn't exist) is always checked before 403 (not authorized) — you can't compare an id against a `groupCreaterId` that doesn't exist.
- `DELETE /groups/{groupId}/members/{userId}` allows **either** the member themselves **or** the group's creator to remove a membership (confirmed extension beyond ASK.md's literal wording).
- `create_group`/`create_task` get `current_user_id: str = Depends(verify_firebase_token)` added as an unused parameter (auth still required, no ownership rule — nothing exists yet to own).
- The Firebase `uid` vs. `User.userId` ID-space mismatch (documented in `OpenPoints.md`) is an accepted, unfixed limitation — tests mock whatever uid each scenario needs.

---

## Task 1: `ForbiddenError` + new repository methods

**Files:**
- Modify: `app/exceptions.py`
- Modify: `app/repositories/task_group_repository.py`
- Modify: `app/repositories/task_repository.py`
- Modify: `tests/repositories/test_task_group_repository.py`
- Modify: `tests/repositories/test_task_repository.py`

**Interfaces:**
- Produces: `ForbiddenError(message: str)` (Tasks 2-6 raise it); `TaskGroupRepository.list_by_task(task_id) -> list[TaskGroupRelationship]`, `TaskGroupRepository.list_by_assignee(assignee_id) -> list[TaskGroupRelationship]`; `TaskRepository.list_by_creator(created_by) -> list[Task]` (Task 5 consumes all three).

- [ ] **Step 1: Write the failing repository tests**

Add to `tests/repositories/test_task_group_repository.py` (after the existing `_seed`/test functions — reuse the file's existing `_make_user_row`/`_make_group_row`/`_make_task_row`/`_make_relationship`/`_seed` helpers):
```python
def test_list_by_task_returns_all_relationships_for_task(db_session):
    _seed(db_session)
    repo = TaskGroupRepository(db_session)
    repo.add(_make_relationship())

    results = repo.list_by_task("task-1")

    assert len(results) == 1
    assert results[0].taskId == "task-1"


def test_list_by_assignee_returns_all_relationships_for_assignee(db_session):
    _seed(db_session)
    repo = TaskGroupRepository(db_session)
    repo.add(_make_relationship())

    results = repo.list_by_assignee("user-1")

    assert len(results) == 1
    assert results[0].assigneeId == "user-1"
```

Add to `tests/repositories/test_task_repository.py` (reuse the file's `_make_user_row`/`_make_task` helpers):
```python
def test_list_by_creator_filters_correctly(db_session):
    _make_user_row(db_session, "user-1")
    _make_user_row(db_session, "user-2")
    repo = TaskRepository(db_session)
    repo.add(_make_task("task-1", "user-1"))
    repo.add(_make_task("task-2", "user-2"))

    results = repo.list_by_creator("user-1")

    assert [t.taskId for t in results] == ["task-1"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest tests/repositories/test_task_group_repository.py tests/repositories/test_task_repository.py -v`
Expected: FAIL with `AttributeError: 'TaskGroupRepository' object has no attribute 'list_by_task'` (and similarly for the other two).

- [ ] **Step 3: Add `ForbiddenError`**

In `app/exceptions.py`, add after `NotFoundError`:
```python
class ForbiddenError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)
```

- [ ] **Step 4: Add the repository methods**

In `app/repositories/task_group_repository.py`, add after `find_by_task_and_group`:
```python
    def list_by_task(self, task_id: str) -> list[TaskGroupRelationship]:
        rows = self._session.query(GroupTaskRow).filter(GroupTaskRow.task_id == task_id).all()
        return [self._to_domain(row) for row in rows]

    def list_by_assignee(self, assignee_id: str) -> list[TaskGroupRelationship]:
        rows = self._session.query(GroupTaskRow).filter(GroupTaskRow.assignee_id == assignee_id).all()
        return [self._to_domain(row) for row in rows]
```

In `app/repositories/task_repository.py`, add after `list_all`:
```python
    def list_by_creator(self, created_by: str) -> list[Task]:
        rows = self._session.query(TaskRow).filter(TaskRow.created_by == created_by).all()
        return [self._to_domain(row) for row in rows]
```

- [ ] **Step 5: Run to verify they pass**

Run: `.venv/bin/pytest tests/repositories/test_task_group_repository.py tests/repositories/test_task_repository.py -v`
Expected: PASS (all tests in both files).

- [ ] **Step 6: Run the full suite and commit**

Run: `.venv/bin/pytest -v` — expect PASS (nothing else touches these yet).
```bash
git add app/exceptions.py app/repositories/task_group_repository.py app/repositories/task_repository.py tests/repositories/test_task_group_repository.py tests/repositories/test_task_repository.py
git commit -m "feat: add ForbiddenError and repository query methods for ownership checks"
```

---

## Task 2: `UserService` ownership

**Files:**
- Modify: `app/services/user_service.py`
- Modify: `tests/unit/test_user_service.py`

**Interfaces:**
- Consumes: `ForbiddenError` (Task 1).
- Produces: `get_user(user_id, current_user_id=None)`, `update_user(..., current_user_id=None)`, `set_status(..., current_user_id=None)` all raise `ForbiddenError` when `current_user_id is not None and current_user_id != user_id`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_user_service.py`:
```python
def test_get_user_raises_forbidden_if_caller_is_not_the_user(service: UserService):
    created = service.create_user(first_name="Ada", last_name="Lovelace")
    with pytest.raises(ForbiddenError):
        service.get_user(created.userId, current_user_id="someone-else")


def test_get_user_succeeds_if_caller_is_the_user(service: UserService):
    created = service.create_user(first_name="Ada", last_name="Lovelace")
    fetched = service.get_user(created.userId, current_user_id=created.userId)
    assert fetched.userId == created.userId


def test_update_user_raises_forbidden_if_caller_is_not_the_user(service: UserService):
    created = service.create_user(first_name="Ada", last_name="Lovelace")
    with pytest.raises(ForbiddenError):
        service.update_user(created.userId, last_name="King", current_user_id="someone-else")


def test_set_status_raises_forbidden_if_caller_is_not_the_user(service: UserService):
    created = service.create_user(first_name="Ada", last_name="Lovelace")
    with pytest.raises(ForbiddenError):
        service.set_status(created.userId, UserStatus.IN_ACTIVE, current_user_id="someone-else")
```
Add `ForbiddenError` to the file's `from app.exceptions import ...` line.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_user_service.py -v`
Expected: FAIL — `TypeError: get_user() got an unexpected keyword argument 'current_user_id'` (and similarly for `update_user`/`set_status`).

- [ ] **Step 3: Implement**

In `app/services/user_service.py`, change:
```python
from app.exceptions import NotFoundError
```
to:
```python
from app.exceptions import ForbiddenError, NotFoundError
```

Change:
```python
    def get_user(self, user_id: str) -> User:
        user = self._repository.get(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found")
        return user

    def update_user(
        self,
        user_id: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        phone_num: Optional[str] = None,
        email_id: Optional[str] = None,
    ) -> User:
        user = self.get_user(user_id)
```
to:
```python
    def get_user(self, user_id: str, current_user_id: Optional[str] = None) -> User:
        user = self._repository.get(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found")
        if current_user_id is not None and current_user_id != user_id:
            raise ForbiddenError(f"User {current_user_id} is not authorized to access user {user_id}")
        return user

    def update_user(
        self,
        user_id: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        phone_num: Optional[str] = None,
        email_id: Optional[str] = None,
        current_user_id: Optional[str] = None,
    ) -> User:
        user = self.get_user(user_id, current_user_id=current_user_id)
```

Change:
```python
    def set_status(self, user_id: str, status: UserStatus) -> User:
        user = self.get_user(user_id)
```
to:
```python
    def set_status(self, user_id: str, status: UserStatus, current_user_id: Optional[str] = None) -> User:
        user = self.get_user(user_id, current_user_id=current_user_id)
```

- [ ] **Step 4: Run to verify they pass, then the full suite**

Run: `.venv/bin/pytest tests/unit/test_user_service.py -v` — expect PASS (all tests).
Run: `.venv/bin/pytest -v` — expect PASS (existing internal callers of `get_user` never pass `current_user_id`, so they're unaffected).

- [ ] **Step 5: Commit**

```bash
git add app/services/user_service.py tests/unit/test_user_service.py
git commit -m "feat: add ownership checks to UserService"
```

---

## Task 3: `GroupService` ownership + DI wiring

**Files:**
- Modify: `app/services/group_service.py`
- Modify: `app/dependencies.py`
- Modify: `tests/unit/test_group_service.py`

**Interfaces:**
- Consumes: `ForbiddenError` (Task 1), `UserGroupRepository.find_by_user_and_group` (existing).
- Produces: `GroupService.__init__(self, repository, user_service, user_group_repository: UserGroupRepository)` — Task 4/6/7's fixtures and DI must use this 3-arg signature. `get_group(group_id, current_user_id=None)`, `get_groups_by_creator(creater_id, current_user_id=None)`, `update_group(..., current_user_id=None)`, `set_status(..., current_user_id=None)`.

- [ ] **Step 1: Update the unit test fixture and write failing tests**

In `tests/unit/test_group_service.py`, change:
```python
from app.repositories.group_repository import GroupRepository
from app.repositories.user_repository import UserRepository
from app.services.group_service import GroupService
from app.services.user_service import UserService


@pytest.fixture
def user_service(db_session) -> UserService:
    return UserService(UserRepository(db_session))


@pytest.fixture
def group_service(db_session, user_service: UserService) -> GroupService:
    return GroupService(GroupRepository(db_session), user_service)
```
to:
```python
from app.repositories.group_repository import GroupRepository
from app.repositories.user_group_repository import UserGroupRepository
from app.repositories.user_repository import UserRepository
from app.services.group_service import GroupService
from app.services.user_service import UserService


@pytest.fixture
def user_service(db_session) -> UserService:
    return UserService(UserRepository(db_session))


@pytest.fixture
def group_service(db_session, user_service: UserService) -> GroupService:
    return GroupService(GroupRepository(db_session), user_service, UserGroupRepository(db_session))
```
Also change the file's `from app.exceptions import NotFoundError` to `from app.exceptions import ForbiddenError, NotFoundError`.

Add new tests at the end of the file:
```python
def test_get_group_raises_forbidden_if_caller_is_not_creator_or_member(
    group_service: GroupService, user_service: UserService
):
    creator = user_service.create_user(first_name="Ada", last_name="Lovelace")
    group = group_service.create_group(
        group_name="Smiths", group_desc=None, group_category="Family", creater_id=creator.userId
    )
    with pytest.raises(ForbiddenError):
        group_service.get_group(group.groupId, current_user_id="outsider")


def test_get_group_succeeds_for_creator(group_service: GroupService, user_service: UserService):
    creator = user_service.create_user(first_name="Ada", last_name="Lovelace")
    group = group_service.create_group(
        group_name="Smiths", group_desc=None, group_category="Family", creater_id=creator.userId
    )
    fetched = group_service.get_group(group.groupId, current_user_id=creator.userId)
    assert fetched.groupId == group.groupId


def test_update_group_raises_forbidden_if_caller_is_not_creator(
    group_service: GroupService, user_service: UserService
):
    creator = user_service.create_user(first_name="Ada", last_name="Lovelace")
    group = group_service.create_group(
        group_name="Smiths", group_desc=None, group_category="Family", creater_id=creator.userId
    )
    with pytest.raises(ForbiddenError):
        group_service.update_group(group.groupId, group_name="New Name", current_user_id="outsider")


def test_get_groups_by_creator_raises_forbidden_if_caller_is_not_the_user(
    group_service: GroupService, user_service: UserService
):
    creator = user_service.create_user(first_name="Ada", last_name="Lovelace")
    with pytest.raises(ForbiddenError):
        group_service.get_groups_by_creator(creator.userId, current_user_id="outsider")
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_group_service.py -v`
Expected: FAIL — `TypeError: GroupService.__init__() missing 1 required positional argument: 'user_group_repository'`.

- [ ] **Step 3: Implement**

In `app/services/group_service.py`, change:
```python
from app.exceptions import NotFoundError
from app.models.enums import GroupStatus
from app.models.group import Group
from app.repositories.group_repository import GroupRepository
from app.services.user_service import UserService


class GroupService:
    def __init__(self, repository: GroupRepository, user_service: UserService):
        self._repository = repository
        self._user_service = user_service
```
to:
```python
from app.exceptions import ForbiddenError, NotFoundError
from app.models.enums import GroupStatus
from app.models.group import Group
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
```

Change:
```python
    def get_group(self, group_id: str) -> Group:
        group = self._repository.get(group_id)
        if group is None:
            raise NotFoundError(f"Group {group_id} not found")
        return group

    def get_groups_by_creator(self, creater_id: str) -> list[Group]:
        return self._repository.list_by_creator(creater_id)

    def update_group(
        self,
        group_id: str,
        group_name: Optional[str] = None,
        group_desc: Optional[str] = None,
        group_icon_url: Optional[str] = None,
    ) -> Group:
        group = self.get_group(group_id)
```
to:
```python
    def get_group(self, group_id: str, current_user_id: Optional[str] = None) -> Group:
        group = self._repository.get(group_id)
        if group is None:
            raise NotFoundError(f"Group {group_id} not found")
        if current_user_id is not None and current_user_id != group.groupCreaterId:
            is_member = self._user_group_repository.find_by_user_and_group(
                current_user_id, group_id
            ) is not None
            if not is_member:
                raise ForbiddenError(
                    f"User {current_user_id} is not authorized to access group {group_id}"
                )
        return group

    def get_groups_by_creator(self, creater_id: str, current_user_id: Optional[str] = None) -> list[Group]:
        if current_user_id is not None and current_user_id != creater_id:
            raise ForbiddenError(
                f"User {current_user_id} is not authorized to view groups created by {creater_id}"
            )
        return self._repository.list_by_creator(creater_id)

    def update_group(
        self,
        group_id: str,
        group_name: Optional[str] = None,
        group_desc: Optional[str] = None,
        group_icon_url: Optional[str] = None,
        current_user_id: Optional[str] = None,
    ) -> Group:
        group = self.get_group(group_id)
        if current_user_id is not None and current_user_id != group.groupCreaterId:
            raise ForbiddenError(f"User {current_user_id} is not authorized to update group {group_id}")
```

Change:
```python
    def set_status(self, group_id: str, status: GroupStatus) -> Group:
        group = self.get_group(group_id)
```
to:
```python
    def set_status(self, group_id: str, status: GroupStatus, current_user_id: Optional[str] = None) -> Group:
        group = self.get_group(group_id)
        if current_user_id is not None and current_user_id != group.groupCreaterId:
            raise ForbiddenError(f"User {current_user_id} is not authorized to update group {group_id}")
```

- [ ] **Step 4: Wire `app/dependencies.py`**

Change:
```python
def get_group_service(
    repository: GroupRepository = Depends(get_group_repository),
    user_service: UserService = Depends(get_user_service),
) -> GroupService:
    return GroupService(repository, user_service)
```
to:
```python
def get_group_service(
    repository: GroupRepository = Depends(get_group_repository),
    user_service: UserService = Depends(get_user_service),
    user_group_repository: UserGroupRepository = Depends(get_user_group_repository),
) -> GroupService:
    return GroupService(repository, user_service, user_group_repository)
```
(`get_user_group_repository` is already defined earlier in this file — no reordering needed since it's defined before `get_group_service`.)

- [ ] **Step 5: Run to verify they pass, then the full suite**

Run: `.venv/bin/pytest tests/unit/test_group_service.py -v` — expect PASS.
Run: `.venv/bin/pytest -v` — expect FAIL in `tests/unit/test_user_group_service.py` and `tests/unit/test_task_group_service.py` (their local `group_service` fixtures still construct `GroupService` with only 2 args) — this is expected and fixed in Tasks 4 and 6.

- [ ] **Step 6: Commit**

```bash
git add app/services/group_service.py app/dependencies.py tests/unit/test_group_service.py
git commit -m "feat: add ownership checks to GroupService"
```

---

## Task 4: `UserGroupService` ownership

**Files:**
- Modify: `app/services/user_group_service.py`
- Modify: `tests/unit/test_user_group_service.py`

**Interfaces:**
- Consumes: `GroupService.get_group(group_id, current_user_id=None)` (Task 3), `ForbiddenError` (Task 1).
- Produces: `associate(..., current_user_id=None)`, `disassociate(..., current_user_id=None)` (self **or** creator), `list_by_group(..., current_user_id=None)`.

- [ ] **Step 1: Fix the fixture and write failing tests**

In `tests/unit/test_user_group_service.py`, change:
```python
from app.repositories.group_repository import GroupRepository
from app.repositories.user_group_repository import UserGroupRepository
from app.repositories.user_repository import UserRepository
from app.services.group_service import GroupService
from app.services.user_group_service import UserGroupService
from app.services.user_service import UserService


@pytest.fixture
def user_service(db_session) -> UserService:
    return UserService(UserRepository(db_session))


@pytest.fixture
def group_service(db_session, user_service: UserService) -> GroupService:
    return GroupService(GroupRepository(db_session), user_service)
```
to:
```python
from app.repositories.group_repository import GroupRepository
from app.repositories.user_group_repository import UserGroupRepository
from app.repositories.user_repository import UserRepository
from app.services.group_service import GroupService
from app.services.user_group_service import UserGroupService
from app.services.user_service import UserService


@pytest.fixture
def user_service(db_session) -> UserService:
    return UserService(UserRepository(db_session))


@pytest.fixture
def group_service(db_session, user_service: UserService) -> GroupService:
    return GroupService(GroupRepository(db_session), user_service, UserGroupRepository(db_session))
```
Change `from app.exceptions import BadRequestError, ErrorCode, NotFoundError` to
`from app.exceptions import BadRequestError, ErrorCode, ForbiddenError, NotFoundError`.

Add new tests at the end of the file:
```python
def test_associate_raises_forbidden_if_caller_is_not_creator_or_member(
    user_group_service: UserGroupService, group_service, user_service
):
    _, group = _make_user_and_group(user_service, group_service)
    member = user_service.create_user(first_name="Bob", last_name="Smith")
    with pytest.raises(ForbiddenError):
        user_group_service.associate(member.userId, group.groupId, "Father", current_user_id="outsider")


def test_list_by_group_raises_forbidden_if_caller_is_not_creator_or_member(
    user_group_service: UserGroupService, group_service, user_service
):
    _, group = _make_user_and_group(user_service, group_service)
    with pytest.raises(ForbiddenError):
        user_group_service.list_by_group(group.groupId, current_user_id="outsider")


def test_disassociate_raises_forbidden_if_caller_is_neither_member_nor_creator(
    user_group_service: UserGroupService, group_service, user_service
):
    creator, group = _make_user_and_group(user_service, group_service)
    member = user_service.create_user(first_name="Bob", last_name="Smith")
    user_group_service.associate(member.userId, group.groupId, "Father")
    with pytest.raises(ForbiddenError):
        user_group_service.disassociate(member.userId, group.groupId, current_user_id="outsider")


def test_disassociate_succeeds_for_creator_removing_someone_else(
    user_group_service: UserGroupService, group_service, user_service
):
    creator, group = _make_user_and_group(user_service, group_service)
    member = user_service.create_user(first_name="Bob", last_name="Smith")
    user_group_service.associate(member.userId, group.groupId, "Father")
    user_group_service.disassociate(member.userId, group.groupId, current_user_id=creator.userId)
    assert user_group_service.list_by_group(group.groupId) == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_user_group_service.py -v`
Expected: FAIL — `TypeError: associate() got an unexpected keyword argument 'current_user_id'`.

- [ ] **Step 3: Implement**

In `app/services/user_group_service.py`, change:
```python
from app.exceptions import BadRequestError, ErrorCode, NotFoundError
```
to:
```python
from app.exceptions import BadRequestError, ErrorCode, ForbiddenError, NotFoundError
```

Change:
```python
    def associate(self, user_id: str, group_id: str, relationship: str) -> UserGroupRelationship:
        self._user_service.get_user(user_id)
        group = self._group_service.get_group(group_id)
```
to:
```python
    def associate(
        self, user_id: str, group_id: str, relationship: str, current_user_id: Optional[str] = None
    ) -> UserGroupRelationship:
        self._user_service.get_user(user_id)
        group = self._group_service.get_group(group_id, current_user_id=current_user_id)
```
(Add `from typing import Optional` to the file's imports.)

Change:
```python
    def disassociate(self, user_id: str, group_id: str) -> None:
        existing = self._repository.find_by_user_and_group(user_id, group_id)
        if existing is None:
            raise NotFoundError(f"User {user_id} is not associated with group {group_id}")
        self._repository.delete(existing.uuid)

    def list_by_group(self, group_id: str) -> list[UserGroupRelationship]:
        self._group_service.get_group(group_id)
        return self._repository.list_by_group(group_id)
```
to:
```python
    def disassociate(self, user_id: str, group_id: str, current_user_id: Optional[str] = None) -> None:
        if current_user_id is not None and current_user_id != user_id:
            group = self._group_service.get_group(group_id)
            if current_user_id != group.groupCreaterId:
                raise ForbiddenError(
                    f"User {current_user_id} is not authorized to remove user {user_id} from group {group_id}"
                )
        existing = self._repository.find_by_user_and_group(user_id, group_id)
        if existing is None:
            raise NotFoundError(f"User {user_id} is not associated with group {group_id}")
        self._repository.delete(existing.uuid)

    def list_by_group(self, group_id: str, current_user_id: Optional[str] = None) -> list[UserGroupRelationship]:
        self._group_service.get_group(group_id, current_user_id=current_user_id)
        return self._repository.list_by_group(group_id)
```

- [ ] **Step 4: Run to verify they pass, then the full suite**

Run: `.venv/bin/pytest tests/unit/test_user_group_service.py -v` — expect PASS.
Run: `.venv/bin/pytest -v` — `tests/unit/test_task_group_service.py` still fails (its `group_service`/`task_service` fixtures aren't fixed yet) — expected, fixed in Task 6.

- [ ] **Step 5: Commit**

```bash
git add app/services/user_group_service.py tests/unit/test_user_group_service.py
git commit -m "feat: add ownership checks to UserGroupService"
```

---

## Task 5: `TaskService` ownership + "my tasks" + DI wiring

**Files:**
- Modify: `app/services/task_service.py`
- Modify: `app/dependencies.py`
- Modify: `tests/unit/test_task_service.py`

**Interfaces:**
- Consumes: `TaskGroupRepository.list_by_task`/`list_by_assignee` (Task 1), `ForbiddenError` (Task 1).
- Produces: `TaskService.__init__(self, repository, user_service, task_group_repository: TaskGroupRepository)` — Task 6/7's fixtures/DI must use this 3-arg signature. `get_task(task_id, current_user_id=None)`, `update_task_meta(..., current_user_id=None)`, `update_task_state(..., current_user_id=None)`, `update_due_date(..., current_user_id=None)`, `get_tasks_for_user(current_user_id) -> list[Task]`.

- [ ] **Step 1: Fix the fixture and write failing tests**

In `tests/unit/test_task_service.py`, change:
```python
from app.repositories.task_repository import TaskRepository
from app.repositories.user_repository import UserRepository
from app.services.task_service import TaskService
from app.services.user_service import UserService


@pytest.fixture
def user_service(db_session) -> UserService:
    return UserService(UserRepository(db_session))


@pytest.fixture
def task_service(db_session, user_service: UserService) -> TaskService:
    return TaskService(TaskRepository(db_session), user_service)
```
to:
```python
from app.repositories.task_group_repository import TaskGroupRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.user_repository import UserRepository
from app.services.task_service import TaskService
from app.services.user_service import UserService


@pytest.fixture
def user_service(db_session) -> UserService:
    return UserService(UserRepository(db_session))


@pytest.fixture
def task_service(db_session, user_service: UserService) -> TaskService:
    return TaskService(TaskRepository(db_session), user_service, TaskGroupRepository(db_session))
```
Change `from app.exceptions import BadRequestError, ErrorCode, NotFoundError` to
`from app.exceptions import BadRequestError, ErrorCode, ForbiddenError, NotFoundError`.

Add new tests at the end of the file:
```python
def test_get_task_raises_forbidden_if_caller_is_neither_creator_nor_assignee(
    task_service: TaskService, user_service: UserService
):
    user = user_service.create_user(first_name="Ada", last_name="Lovelace")
    task = task_service.create_task(task_title="Buy milk", created_by=user.userId)
    with pytest.raises(ForbiddenError):
        task_service.get_task(task.taskId, current_user_id="outsider")


def test_get_task_succeeds_for_creator(task_service: TaskService, user_service: UserService):
    user = user_service.create_user(first_name="Ada", last_name="Lovelace")
    task = task_service.create_task(task_title="Buy milk", created_by=user.userId)
    fetched = task_service.get_task(task.taskId, current_user_id=user.userId)
    assert fetched.taskId == task.taskId


def test_update_task_meta_raises_forbidden_if_caller_is_not_creator(
    task_service: TaskService, user_service: UserService
):
    user = user_service.create_user(first_name="Ada", last_name="Lovelace")
    task = task_service.create_task(task_title="Buy milk", created_by=user.userId)
    with pytest.raises(ForbiddenError):
        task_service.update_task_meta(
            task.taskId, updated_by=user.userId, task_title="New", current_user_id="outsider"
        )


def test_get_tasks_for_user_returns_created_and_assigned_sorted_by_latest(task_service, user_service):
    import time

    from app.repositories.task_group_repository import TaskGroupRepository
    from app.repositories.user_group_repository import UserGroupRepository
    from app.repositories.group_repository import GroupRepository
    from app.services.group_service import GroupService
    from app.services.user_group_service import UserGroupService

    creator = user_service.create_user(first_name="Ada", last_name="Lovelace")
    assignee = user_service.create_user(first_name="Bob", last_name="Smith")
    task_a = task_service.create_task(task_title="Task A", created_by=creator.userId)
    time.sleep(0.01)
    task_b = task_service.create_task(task_title="Task B", created_by=assignee.userId)

    group_repo = GroupRepository(task_service._repository._session)  # reuse the same db_session
    group_service = GroupService(group_repo, user_service, UserGroupRepository(task_service._repository._session))
    group = group_service.create_group(
        group_name="Smiths", group_desc=None, group_category="Family", creater_id=creator.userId
    )
    user_group_service = UserGroupService(
        UserGroupRepository(task_service._repository._session), user_service, group_service
    )
    user_group_service.associate(assignee.userId, group.groupId, "Member")
    task_group_repo = TaskGroupRepository(task_service._repository._session)
    from app.services.task_group_service import TaskGroupService

    task_group_service = TaskGroupService(
        task_group_repo, task_service, group_service, user_service, user_group_service
    )
    task_group_service.assign(task_b.taskId, group.groupId, creator.userId)

    results = task_service.get_tasks_for_user(creator.userId)

    result_ids = [t.taskId for t in results]
    assert set(result_ids) == {task_a.taskId, task_b.taskId}
    assert result_ids[0] == task_b.taskId  # most recently created/updated first
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_task_service.py -v`
Expected: FAIL — `TypeError: TaskService.__init__() missing 1 required positional argument: 'task_group_repository'`.

- [ ] **Step 3: Implement**

In `app/services/task_service.py`, change:
```python
from app.exceptions import BadRequestError, ErrorCode, NotFoundError
from app.models.enums import TaskState
from app.models.task import Task
from app.repositories.base import BaseRepository
from app.services.user_service import UserService


class TaskService:
    def __init__(self, repository: BaseRepository[Task], user_service: UserService):
        self._repository = repository
        self._user_service = user_service
```
to:
```python
from app.exceptions import BadRequestError, ErrorCode, ForbiddenError, NotFoundError
from app.models.enums import TaskState
from app.models.task import Task
from app.repositories.base import BaseRepository
from app.repositories.task_group_repository import TaskGroupRepository
from app.services.user_service import UserService


class TaskService:
    def __init__(
        self,
        repository: BaseRepository[Task],
        user_service: UserService,
        task_group_repository: TaskGroupRepository,
    ):
        self._repository = repository
        self._user_service = user_service
        self._task_group_repository = task_group_repository
```

Change:
```python
    def get_task(self, task_id: str) -> Task:
        task = self._repository.get(task_id)
        if task is None:
            raise NotFoundError(f"Task {task_id} not found")
        return task

    def update_task_meta(
        self,
        task_id: str,
        updated_by: str,
        task_title: Optional[str] = None,
        task_desc: Optional[str] = None,
    ) -> Task:
        self._user_service.get_user(updated_by)
        task = self.get_task(task_id)
```
to:
```python
    def get_task(self, task_id: str, current_user_id: Optional[str] = None) -> Task:
        task = self._repository.get(task_id)
        if task is None:
            raise NotFoundError(f"Task {task_id} not found")
        if current_user_id is not None and current_user_id != task.createdBy:
            assignments = self._task_group_repository.list_by_task(task_id)
            is_assignee = any(rel.assigneeId == current_user_id for rel in assignments)
            if not is_assignee:
                raise ForbiddenError(f"User {current_user_id} is not authorized to access task {task_id}")
        return task

    def update_task_meta(
        self,
        task_id: str,
        updated_by: str,
        task_title: Optional[str] = None,
        task_desc: Optional[str] = None,
        current_user_id: Optional[str] = None,
    ) -> Task:
        self._user_service.get_user(updated_by)
        task = self.get_task(task_id)
        if current_user_id is not None and current_user_id != task.createdBy:
            raise ForbiddenError(f"User {current_user_id} is not authorized to update task {task_id}")
```

Change:
```python
    def update_task_state(self, task_id: str, updated_by: str, new_state: TaskState) -> Task:
        self._user_service.get_user(updated_by)
        task = self.get_task(task_id)
        if task.taskState == new_state:
```
to:
```python
    def update_task_state(
        self, task_id: str, updated_by: str, new_state: TaskState, current_user_id: Optional[str] = None
    ) -> Task:
        self._user_service.get_user(updated_by)
        task = self.get_task(task_id, current_user_id=current_user_id)
        if task.taskState == new_state:
```

Change:
```python
    def update_due_date(self, task_id: str, updated_by: str, due_date: Optional[datetime]) -> Task:
        self._user_service.get_user(updated_by)
        task = self.get_task(task_id)
```
to:
```python
    def update_due_date(
        self,
        task_id: str,
        updated_by: str,
        due_date: Optional[datetime],
        current_user_id: Optional[str] = None,
    ) -> Task:
        self._user_service.get_user(updated_by)
        task = self.get_task(task_id, current_user_id=current_user_id)
```

Add at the end of the class:
```python
    def get_tasks_for_user(self, current_user_id: str) -> list[Task]:
        created = self._repository.list_by_creator(current_user_id)
        seen_ids = {t.taskId for t in created}
        assigned_tasks = []
        for rel in self._task_group_repository.list_by_assignee(current_user_id):
            if rel.taskId in seen_ids:
                continue
            task = self._repository.get(rel.taskId)
            if task is not None:
                assigned_tasks.append(task)
                seen_ids.add(rel.taskId)
        all_tasks = created + assigned_tasks
        all_tasks.sort(key=lambda t: t.updatedAt or t.createdAt, reverse=True)
        return all_tasks
```

- [ ] **Step 4: Wire `app/dependencies.py`**

Change:
```python
def get_task_service(
    repository: TaskRepository = Depends(get_task_repository),
    user_service: UserService = Depends(get_user_service),
) -> TaskService:
    return TaskService(repository, user_service)
```
to:
```python
def get_task_service(
    repository: TaskRepository = Depends(get_task_repository),
    user_service: UserService = Depends(get_user_service),
    task_group_repository: TaskGroupRepository = Depends(get_task_group_repository),
) -> TaskService:
    return TaskService(repository, user_service, task_group_repository)
```
(`get_task_group_repository` is defined later in the file than `get_task_service` currently — move `get_task_service`'s definition to AFTER `get_task_group_repository`'s definition, or move `get_task_group_repository`'s definition earlier, so the referenced provider exists at function-definition time. Simplest: cut the existing `get_task_group_repository` function block and paste it directly above `get_task_service`.)

- [ ] **Step 5: Run to verify they pass, then the full suite**

Run: `.venv/bin/pytest tests/unit/test_task_service.py -v` — expect PASS.
Run: `.venv/bin/pytest -v` — `tests/unit/test_task_group_service.py` still fails (fixtures not fixed yet) — expected, fixed in Task 6.

- [ ] **Step 6: Commit**

```bash
git add app/services/task_service.py app/dependencies.py tests/unit/test_task_service.py
git commit -m "feat: add ownership checks and get_tasks_for_user to TaskService"
```

---

## Task 6: `TaskGroupService` ownership

**Files:**
- Modify: `app/services/task_group_service.py`
- Modify: `tests/unit/test_task_group_service.py`

**Interfaces:**
- Consumes: `TaskService.get_task` (unchanged signature, called without `current_user_id` for internal reads), `ForbiddenError` (Task 1).
- Produces: `assign(..., current_user_id=None)`, `unassign(..., current_user_id=None)` both raise `ForbiddenError` when `current_user_id != task.createdBy`.

- [ ] **Step 1: Fix the fixtures and write failing tests**

In `tests/unit/test_task_group_service.py`, change:
```python
@pytest.fixture
def group_service(db_session, user_service: UserService) -> GroupService:
    return GroupService(GroupRepository(db_session), user_service)


@pytest.fixture
def task_service(db_session, user_service: UserService) -> TaskService:
    return TaskService(TaskRepository(db_session), user_service)
```
to:
```python
@pytest.fixture
def group_service(db_session, user_service: UserService) -> GroupService:
    return GroupService(GroupRepository(db_session), user_service, UserGroupRepository(db_session))


@pytest.fixture
def task_service(db_session, user_service: UserService) -> TaskService:
    return TaskService(TaskRepository(db_session), user_service, TaskGroupRepository(db_session))
```
Change `from app.exceptions import BadRequestError, ErrorCode, NotFoundError` to
`from app.exceptions import BadRequestError, ErrorCode, ForbiddenError, NotFoundError`.

Add new tests at the end of the file:
```python
def test_assign_raises_forbidden_if_caller_is_not_task_creator(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    _, assignee, group, task = _setup(user_service, group_service, task_service, user_group_service)
    with pytest.raises(ForbiddenError):
        task_group_service.assign(task.taskId, group.groupId, assignee.userId, current_user_id="outsider")


def test_unassign_raises_forbidden_if_caller_is_not_task_creator(
    task_group_service, user_service, group_service, task_service, user_group_service
):
    _, assignee, group, task = _setup(user_service, group_service, task_service, user_group_service)
    task_group_service.assign(task.taskId, group.groupId, assignee.userId)
    with pytest.raises(ForbiddenError):
        task_group_service.unassign(
            task.taskId, group.groupId, assignee.userId, current_user_id="outsider"
        )
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_task_group_service.py -v`
Expected: FAIL — `TypeError: GroupService.__init__() missing 1 required positional argument`.

- [ ] **Step 3: Implement**

In `app/services/task_group_service.py`, change:
```python
from app.exceptions import BadRequestError, ErrorCode, NotFoundError
```
to:
```python
from app.exceptions import BadRequestError, ErrorCode, ForbiddenError, NotFoundError
```

Change:
```python
    def assign(self, task_id: str, group_id: str, assignee_id: str) -> TaskGroupRelationship:
        task = self._task_service.get_task(task_id)
        self._group_service.get_group(group_id)
        self._user_service.get_user(assignee_id)
        if assignee_id == task.createdBy:
```
to:
```python
    def assign(
        self, task_id: str, group_id: str, assignee_id: str, current_user_id: Optional[str] = None
    ) -> TaskGroupRelationship:
        task = self._task_service.get_task(task_id)
        self._group_service.get_group(group_id)
        self._user_service.get_user(assignee_id)
        if current_user_id is not None and current_user_id != task.createdBy:
            raise ForbiddenError(f"User {current_user_id} is not authorized to assign task {task_id}")
        if assignee_id == task.createdBy:
```
(Add `from typing import Optional` to the file's imports.)

Change:
```python
    def unassign(self, task_id: str, group_id: str, assignee_id: str) -> TaskGroupRelationship:
        existing = self._repository.find_by_task_and_group(task_id, group_id)
```
to:
```python
    def unassign(
        self, task_id: str, group_id: str, assignee_id: str, current_user_id: Optional[str] = None
    ) -> TaskGroupRelationship:
        task = self._task_service.get_task(task_id)
        if current_user_id is not None and current_user_id != task.createdBy:
            raise ForbiddenError(f"User {current_user_id} is not authorized to unassign task {task_id}")
        existing = self._repository.find_by_task_and_group(task_id, group_id)
```

- [ ] **Step 4: Run to verify they pass, then the full suite**

Run: `.venv/bin/pytest tests/unit/test_task_group_service.py -v` — expect PASS.
Run: `.venv/bin/pytest -v` — expect PASS (all unit tests fixed; integration tests not yet touched — Task 7/9 handle those; this run may still show integration failures if `tests/conftest.py`'s fixtures don't build services correctly yet — proceed to Task 7).

- [ ] **Step 5: Commit**

```bash
git add app/services/task_group_service.py tests/unit/test_task_group_service.py
git commit -m "feat: add ownership checks to TaskGroupService"
```

---

## Task 7: Test infrastructure — `authenticate_as` + fixture constructor fixes

**Files:**
- Modify: `tests/conftest.py`

**Interfaces:**
- Produces: `authenticate_as(user_id: str) -> None` fixture — Task 9's integration tests call this to switch the mocked caller identity mid-test.

- [ ] **Step 1: Fix `client`/`unauthenticated_client`'s constructor calls**

In `tests/conftest.py`, both fixtures currently have:
```python
    user_service = UserService(user_repo)
    group_service = GroupService(group_repo, user_service)
    user_group_service = UserGroupService(user_group_repo, user_service, group_service)
    task_service = TaskService(task_repo, user_service)
```
Change (in BOTH `client` and `unauthenticated_client`) to:
```python
    user_service = UserService(user_repo)
    group_service = GroupService(group_repo, user_service, user_group_repo)
    user_group_service = UserGroupService(user_group_repo, user_service, group_service)
    task_service = TaskService(task_repo, user_service, task_group_repo)
```

- [ ] **Step 2: Add the `authenticate_as` fixture**

Add after the `client` fixture, before `unauthenticated_client`:
```python
@pytest.fixture
def authenticate_as():
    def _authenticate_as(user_id: str) -> None:
        app.dependency_overrides[verify_firebase_token] = lambda: user_id
    return _authenticate_as
```

- [ ] **Step 3: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: unit tests and repository tests PASS; MANY integration tests now FAIL with 403 (since real created users' ids never match the default `"test-firebase-uid"`) — this is the expected, temporary state fixed by Task 9. Confirm the failures are all 403-related (not errors/crashes) before proceeding.

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py
git commit -m "test: add authenticate_as fixture and fix service constructor wiring"
```

---

## Task 8: Router wiring — move auth to function argument, thread ownership, add 403 handling, new endpoint

**Files:**
- Modify: `app/api/v1/users.py`
- Modify: `app/api/v1/groups.py`
- Modify: `app/api/v1/user_group.py`
- Modify: `app/api/v1/tasks.py`
- Modify: `app/api/v1/task_group.py`

**Interfaces:**
- Consumes: every gated service method's `current_user_id` param (Tasks 2-6).
- Produces: `GET /api/v1/tasks` (new route, `list_my_tasks`) — no later task depends on it.

- [ ] **Step 1: `app/api/v1/users.py`**

Remove `dependencies=[Depends(verify_firebase_token)]` from the 3 decorators, add `current_user_id: str = Depends(verify_firebase_token)` as a function parameter on each, thread it through, add `ForbiddenError` handling:
```python
@router.get(
    "/{user_id}",
    response_model=UserResponse,
    responses={404: {"description": "User not found"}, 403: {"description": "Not authorized"}},
)
def get_user(
    user_id: str,
    current_user_id: str = Depends(verify_firebase_token),
    service: UserService = Depends(get_user_service),
) -> UserResponse:
    try:
        user = service.get_user(user_id, current_user_id=current_user_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return _to_response(user)


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    responses={404: {"description": "User not found"}, 403: {"description": "Not authorized"}},
)
def update_user(
    user_id: str,
    payload: UserUpdateRequest,
    current_user_id: str = Depends(verify_firebase_token),
    service: UserService = Depends(get_user_service),
) -> UserResponse:
    try:
        user = service.update_user(
            user_id,
            first_name=payload.firstName,
            last_name=payload.lastName,
            phone_num=payload.phoneNum,
            email_id=payload.emailId,
            current_user_id=current_user_id,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return _to_response(user)


@router.patch(
    "/{user_id}/status",
    response_model=UserResponse,
    responses={404: {"description": "User not found"}, 403: {"description": "Not authorized"}},
)
def update_user_status(
    user_id: str,
    payload: UserStatusUpdateRequest,
    current_user_id: str = Depends(verify_firebase_token),
    service: UserService = Depends(get_user_service),
) -> UserResponse:
    try:
        user = service.set_status(user_id, payload.userStatus, current_user_id=current_user_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return _to_response(user)
```
Change the file's import line `from app.exceptions import NotFoundError` to `from app.exceptions import ForbiddenError, NotFoundError`. `create_user` is untouched.

- [ ] **Step 2: `app/api/v1/groups.py`**

Change the `APIRouter(...)` construction from:
```python
router = APIRouter(
    prefix="/api/v1", tags=["groups"], dependencies=[Depends(verify_firebase_token)]
)
```
to:
```python
router = APIRouter(prefix="/api/v1", tags=["groups"])
```

Change `create_group` to add the unused param:
```python
def create_group(
    payload: GroupCreateRequest,
    current_user_id: str = Depends(verify_firebase_token),
    service: GroupService = Depends(get_group_service),
) -> GroupResponse:
```
(body unchanged).

Change `get_group`:
```python
@router.get(
    "/groups/{group_id}",
    response_model=GroupResponse,
    responses={404: {"description": "Group not found"}, 403: {"description": "Not authorized"}},
)
def get_group(
    group_id: str,
    current_user_id: str = Depends(verify_firebase_token),
    service: GroupService = Depends(get_group_service),
) -> GroupResponse:
    try:
        group = service.get_group(group_id, current_user_id=current_user_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return _to_response(group)
```

Change `get_groups_by_creator` (this one had no try/except before):
```python
@router.get(
    "/users/{user_id}/groups",
    response_model=list[GroupResponse],
    responses={403: {"description": "Not authorized"}},
)
def get_groups_by_creator(
    user_id: str,
    current_user_id: str = Depends(verify_firebase_token),
    service: GroupService = Depends(get_group_service),
) -> list[GroupResponse]:
    try:
        groups = service.get_groups_by_creator(user_id, current_user_id=current_user_id)
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return [_to_response(group) for group in groups]
```

Change `update_group`/`update_group_status` the same way as `get_group` (add param, pass `current_user_id=current_user_id`, add `ForbiddenError` handling alongside existing `NotFoundError`):
```python
@router.patch(
    "/groups/{group_id}",
    response_model=GroupResponse,
    responses={404: {"description": "Group not found"}, 403: {"description": "Not authorized"}},
)
def update_group(
    group_id: str,
    payload: GroupUpdateRequest,
    current_user_id: str = Depends(verify_firebase_token),
    service: GroupService = Depends(get_group_service),
) -> GroupResponse:
    try:
        group = service.update_group(
            group_id,
            group_name=payload.groupName,
            group_desc=payload.groupDesc,
            group_icon_url=payload.groupIconUrl,
            current_user_id=current_user_id,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return _to_response(group)


@router.patch(
    "/groups/{group_id}/status",
    response_model=GroupResponse,
    responses={404: {"description": "Group not found"}, 403: {"description": "Not authorized"}},
)
def update_group_status(
    group_id: str,
    payload: GroupStatusUpdateRequest,
    current_user_id: str = Depends(verify_firebase_token),
    service: GroupService = Depends(get_group_service),
) -> GroupResponse:
    try:
        group = service.set_status(group_id, payload.groupStatus, current_user_id=current_user_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return _to_response(group)
```
Change the file's import line to `from app.exceptions import ForbiddenError, NotFoundError`.

- [ ] **Step 3: `app/api/v1/user_group.py`**

Change the `APIRouter(...)` construction to remove `dependencies=[...]`:
```python
router = APIRouter(prefix="/api/v1/groups", tags=["user-group"])
```

Change `associate_user`:
```python
def associate_user(
    group_id: str,
    payload: UserGroupAssociateRequest,
    current_user_id: str = Depends(verify_firebase_token),
    service: UserGroupService = Depends(get_user_group_service),
) -> UserGroupResponse:
    try:
        relationship = service.associate(
            payload.userId, group_id, payload.relationship, current_user_id=current_user_id
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BadRequestError as exc:
        raise HTTPException(
            status_code=exc.http_code,
            detail=ErrorDetail(errorCode=exc.error_code, message=exc.message).model_dump(),
        ) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return UserGroupResponse(**relationship.model_dump())
```

Change `get_group_members`:
```python
def get_group_members(
    group_id: str,
    current_user_id: str = Depends(verify_firebase_token),
    service: UserGroupService = Depends(get_user_group_service),
) -> list[UserGroupResponse]:
    try:
        relationships = service.list_by_group(group_id, current_user_id=current_user_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return [UserGroupResponse(**r.model_dump()) for r in relationships]
```

Change `disassociate_user`:
```python
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
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
```
Change the file's import line to `from app.exceptions import BadRequestError, ForbiddenError, NotFoundError`.

- [ ] **Step 4: `app/api/v1/tasks.py`**

Change the `APIRouter(...)` construction:
```python
router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])
```

Change `create_task` to add the unused param (body unchanged otherwise):
```python
def create_task(
    payload: TaskCreateRequest,
    current_user_id: str = Depends(verify_firebase_token),
    service: TaskService = Depends(get_task_service),
) -> TaskResponse:
```

Add the new route directly after `create_task`:
```python
@router.get("", response_model=list[TaskResponse])
def list_my_tasks(
    current_user_id: str = Depends(verify_firebase_token),
    service: TaskService = Depends(get_task_service),
) -> list[TaskResponse]:
    tasks = service.get_tasks_for_user(current_user_id)
    return [_to_response(t) for t in tasks]
```

Change `get_task`:
```python
@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    responses={404: {"description": "Task not found"}, 403: {"description": "Not authorized"}},
)
def get_task(
    task_id: str,
    current_user_id: str = Depends(verify_firebase_token),
    service: TaskService = Depends(get_task_service),
) -> TaskResponse:
    try:
        task = service.get_task(task_id, current_user_id=current_user_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return _to_response(task)
```

Change `update_task_meta`:
```python
@router.patch(
    "/{task_id}",
    response_model=TaskResponse,
    responses={404: {"description": "Task or updating user not found"}, 403: {"description": "Not authorized"}},
)
def update_task_meta(
    task_id: str,
    payload: TaskMetaUpdateRequest,
    current_user_id: str = Depends(verify_firebase_token),
    service: TaskService = Depends(get_task_service),
) -> TaskResponse:
    try:
        task = service.update_task_meta(
            task_id,
            updated_by=payload.updatedBy,
            task_title=payload.taskTitle,
            task_desc=payload.taskDesc,
            current_user_id=current_user_id,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return _to_response(task)
```

Change `update_task_state`:
```python
def update_task_state(
    task_id: str,
    payload: TaskStateUpdateRequest,
    current_user_id: str = Depends(verify_firebase_token),
    service: TaskService = Depends(get_task_service),
) -> TaskResponse:
    try:
        task = service.update_task_state(
            task_id, updated_by=payload.updatedBy, new_state=payload.taskState, current_user_id=current_user_id
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BadRequestError as exc:
        raise HTTPException(
            status_code=exc.http_code,
            detail=ErrorDetail(errorCode=exc.error_code, message=exc.message).model_dump(),
        ) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return _to_response(task)
```
(Add `403: {"description": "Not authorized"}` to this route's `responses=` dict too.)

Change `update_due_date`:
```python
def update_due_date(
    task_id: str,
    payload: TaskDueDateUpdateRequest,
    current_user_id: str = Depends(verify_firebase_token),
    service: TaskService = Depends(get_task_service),
) -> TaskResponse:
    try:
        task = service.update_due_date(
            task_id, updated_by=payload.updatedBy, due_date=payload.taskDueDate, current_user_id=current_user_id
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return _to_response(task)
```
Change the file's import line to `from app.exceptions import BadRequestError, ForbiddenError, NotFoundError`.

- [ ] **Step 5: `app/api/v1/task_group.py`**

Change the `APIRouter(...)` construction:
```python
router = APIRouter(
    prefix="/api/v1/groups/{group_id}/tasks/{task_id}/assignee", tags=["task-group"]
)
```

Change `assign_task`:
```python
def assign_task(
    group_id: str,
    task_id: str,
    payload: TaskGroupAssignRequest,
    current_user_id: str = Depends(verify_firebase_token),
    service: TaskGroupService = Depends(get_task_group_service),
) -> TaskGroupResponse:
    try:
        relationship = service.assign(
            task_id, group_id, payload.assigneeId, current_user_id=current_user_id
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BadRequestError as exc:
        raise HTTPException(
            status_code=exc.http_code,
            detail=ErrorDetail(errorCode=exc.error_code, message=exc.message).model_dump(),
        ) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return TaskGroupResponse(**relationship.model_dump())
```

Change `unassign_task`:
```python
@router.delete(
    "/{assignee_id}",
    response_model=TaskGroupResponse,
    responses={404: {"description": "No matching task-group assignment found for that assignee"}, 403: {"description": "Not authorized"}},
)
def unassign_task(
    group_id: str,
    task_id: str,
    assignee_id: str,
    current_user_id: str = Depends(verify_firebase_token),
    service: TaskGroupService = Depends(get_task_group_service),
) -> TaskGroupResponse:
    try:
        relationship = service.unassign(task_id, group_id, assignee_id, current_user_id=current_user_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return TaskGroupResponse(**relationship.model_dump())
```
Change the file's import line to `from app.exceptions import BadRequestError, ForbiddenError, NotFoundError`.

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: unit/repository tests PASS; MANY integration tests still fail (needing `authenticate_as` calls — fixed in Task 9). Confirm no crashes/import errors, only assertion failures on status codes.

- [ ] **Step 7: Commit**

```bash
git add app/api/v1/users.py app/api/v1/groups.py app/api/v1/user_group.py app/api/v1/tasks.py app/api/v1/task_group.py
git commit -m "feat: move Firebase auth to a function argument and enforce ownership in all routers"
```

---

## Task 9: Integration test updates

**Files:**
- Modify: `tests/integration/test_users_api.py`
- Modify: `tests/integration/test_groups_api.py`
- Modify: `tests/integration/test_user_group_api.py`
- Modify: `tests/integration/test_tasks_api.py`
- Modify: `tests/integration/test_task_group_api.py`
- Modify: `tests/integration/test_full_lifecycle_api.py`

**Interfaces:**
- Consumes: `authenticate_as` fixture (Task 7), every router change (Task 8).

- [ ] **Step 1: `tests/integration/test_users_api.py` — replace the file**

```python
def test_create_and_fetch_user(client, authenticate_as):
    create_response = client.post(
        "/api/v1/users",
        json={"firstName": "Ada", "lastName": "Lovelace", "emailId": "ada@example.com"},
    )
    assert create_response.status_code == 201
    body = create_response.json()
    assert body["name"] == {"firstName": "Ada", "lastName": "Lovelace"}
    assert body["userStatus"] == "ACTIVE"
    user_id = body["userId"]

    authenticate_as(user_id)
    fetch_response = client.get(f"/api/v1/users/{user_id}")
    assert fetch_response.status_code == 200
    assert fetch_response.json()["userId"] == user_id


def test_fetch_unknown_user_returns_404(client):
    response = client.get("/api/v1/users/does-not-exist")
    assert response.status_code == 404


def test_get_user_wrong_caller_returns_403(client):
    user_id = client.post(
        "/api/v1/users", json={"firstName": "Ada", "lastName": "Lovelace"}
    ).json()["userId"]

    response = client.get(f"/api/v1/users/{user_id}")
    assert response.status_code == 403


def test_update_user_fields(client, authenticate_as):
    user_id = client.post(
        "/api/v1/users", json={"firstName": "Ada", "lastName": "Lovelace"}
    ).json()["userId"]

    authenticate_as(user_id)
    response = client.patch(f"/api/v1/users/{user_id}", json={"lastName": "King"})
    assert response.status_code == 200
    assert response.json()["name"]["lastName"] == "King"


def test_update_user_wrong_caller_returns_403(client):
    user_id = client.post(
        "/api/v1/users", json={"firstName": "Ada", "lastName": "Lovelace"}
    ).json()["userId"]

    response = client.patch(f"/api/v1/users/{user_id}", json={"lastName": "King"})
    assert response.status_code == 403


def test_update_user_status(client, authenticate_as):
    user_id = client.post(
        "/api/v1/users", json={"firstName": "Ada", "lastName": "Lovelace"}
    ).json()["userId"]

    authenticate_as(user_id)
    response = client.patch(
        f"/api/v1/users/{user_id}/status", json={"userStatus": "IN-ACTIVE"}
    )
    assert response.status_code == 200
    assert response.json()["userStatus"] == "IN-ACTIVE"
```

- [ ] **Step 2: `tests/integration/test_groups_api.py` — replace the file**

```python
def _create_user(client, first_name="Ada", last_name="Lovelace"):
    response = client.post("/api/v1/users", json={"firstName": first_name, "lastName": last_name})
    return response.json()["userId"]


def test_create_group_for_unknown_creator_returns_404(client):
    response = client.post(
        "/api/v1/groups",
        json={"groupName": "Smiths", "groupCategory": "Family", "groupCreaterId": "unknown"},
    )
    assert response.status_code == 404


def test_create_and_fetch_group(client, authenticate_as):
    creator_id = _create_user(client)
    create_response = client.post(
        "/api/v1/groups",
        json={
            "groupName": "Smiths",
            "groupDesc": "Family group",
            "groupCategory": "Family",
            "groupCreaterId": creator_id,
        },
    )
    assert create_response.status_code == 201
    group_id = create_response.json()["groupId"]

    authenticate_as(creator_id)
    fetch_response = client.get(f"/api/v1/groups/{group_id}")
    assert fetch_response.status_code == 200
    assert fetch_response.json()["groupCreaterId"] == creator_id


def test_get_group_non_member_non_creator_returns_403(client):
    creator_id = _create_user(client)
    group_id = client.post(
        "/api/v1/groups",
        json={"groupName": "Smiths", "groupCategory": "Family", "groupCreaterId": creator_id},
    ).json()["groupId"]

    response = client.get(f"/api/v1/groups/{group_id}")
    assert response.status_code == 403


def test_get_groups_by_creator(client, authenticate_as):
    creator_id = _create_user(client)
    client.post(
        "/api/v1/groups",
        json={"groupName": "Smiths", "groupCategory": "Family", "groupCreaterId": creator_id},
    )

    authenticate_as(creator_id)
    response = client.get(f"/api/v1/users/{creator_id}/groups")
    assert response.status_code == 200
    groups = response.json()
    assert len(groups) == 1
    assert groups[0]["groupName"] == "Smiths"


def test_get_groups_by_creator_wrong_caller_returns_403(client):
    creator_id = _create_user(client)

    response = client.get(f"/api/v1/users/{creator_id}/groups")
    assert response.status_code == 403


def test_update_group_ignores_category_field(client, authenticate_as):
    creator_id = _create_user(client)
    group_id = client.post(
        "/api/v1/groups",
        json={"groupName": "Smiths", "groupCategory": "Family", "groupCreaterId": creator_id},
    ).json()["groupId"]

    authenticate_as(creator_id)
    response = client.patch(f"/api/v1/groups/{group_id}", json={"groupName": "The Smiths"})
    assert response.status_code == 200
    body = response.json()
    assert body["groupName"] == "The Smiths"
    assert body["groupCategory"] == "Family"


def test_update_group_non_creator_returns_403(client):
    creator_id = _create_user(client)
    group_id = client.post(
        "/api/v1/groups",
        json={"groupName": "Smiths", "groupCategory": "Family", "groupCreaterId": creator_id},
    ).json()["groupId"]

    response = client.patch(f"/api/v1/groups/{group_id}", json={"groupName": "The Smiths"})
    assert response.status_code == 403


def test_update_group_status(client, authenticate_as):
    creator_id = _create_user(client)
    group_id = client.post(
        "/api/v1/groups",
        json={"groupName": "Smiths", "groupCategory": "Family", "groupCreaterId": creator_id},
    ).json()["groupId"]

    authenticate_as(creator_id)
    response = client.patch(f"/api/v1/groups/{group_id}/status", json={"groupStatus": "IN-ACTIVE"})
    assert response.status_code == 200
    assert response.json()["groupStatus"] == "IN-ACTIVE"
```

- [ ] **Step 3: `tests/integration/test_user_group_api.py` — replace the file**

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


def test_associate_user_to_group(client, authenticate_as):
    creator_id = _create_user(client)
    member_id = _create_user(client, first_name="Bob", last_name="Smith")
    group_id = _create_group(client, creator_id)

    authenticate_as(creator_id)
    response = client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": member_id, "relationship": "Father"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["userId"] == member_id
    assert body["groupId"] == group_id
    assert body["relationship"] == "Father"


def test_associate_non_member_non_creator_returns_403(client):
    creator_id = _create_user(client)
    member_id = _create_user(client, first_name="Bob", last_name="Smith")
    group_id = _create_group(client, creator_id)

    response = client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": member_id, "relationship": "Father"}
    )
    assert response.status_code == 403


def test_associate_duplicate_returns_400(client, authenticate_as):
    creator_id = _create_user(client)
    member_id = _create_user(client, first_name="Bob", last_name="Smith")
    group_id = _create_group(client, creator_id)
    authenticate_as(creator_id)
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


def test_associate_group_creator_returns_400(client, authenticate_as):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)

    authenticate_as(creator_id)
    response = client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": creator_id, "relationship": "Father"}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["errorCode"] == "ERR_TASKS_006"


def test_disassociate_user_from_group(client, authenticate_as):
    creator_id = _create_user(client)
    member_id = _create_user(client, first_name="Bob", last_name="Smith")
    group_id = _create_group(client, creator_id)
    authenticate_as(creator_id)
    client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": member_id, "relationship": "Father"}
    )

    response = client.delete(f"/api/v1/groups/{group_id}/members/{member_id}")
    assert response.status_code == 204


def test_disassociate_self_succeeds(client, authenticate_as):
    creator_id = _create_user(client)
    member_id = _create_user(client, first_name="Bob", last_name="Smith")
    group_id = _create_group(client, creator_id)
    authenticate_as(creator_id)
    client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": member_id, "relationship": "Father"}
    )

    authenticate_as(member_id)
    response = client.delete(f"/api/v1/groups/{group_id}/members/{member_id}")
    assert response.status_code == 204


def test_disassociate_wrong_user_returns_403(client, authenticate_as):
    creator_id = _create_user(client)
    member_id = _create_user(client, first_name="Bob", last_name="Smith")
    outsider_id = _create_user(client, first_name="Cara", last_name="Jones")
    group_id = _create_group(client, creator_id)
    authenticate_as(creator_id)
    client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": member_id, "relationship": "Father"}
    )

    authenticate_as(outsider_id)
    response = client.delete(f"/api/v1/groups/{group_id}/members/{member_id}")
    assert response.status_code == 403


def test_disassociate_unknown_association_returns_404(client, authenticate_as):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)

    authenticate_as(creator_id)
    response = client.delete(f"/api/v1/groups/{group_id}/members/{creator_id}")
    assert response.status_code == 404


def test_get_group_members_returns_associated_users(client, authenticate_as):
    creator_id = _create_user(client)
    member_id = _create_user(client, first_name="Bob", last_name="Smith")
    group_id = _create_group(client, creator_id)
    authenticate_as(creator_id)
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


def test_get_group_members_non_member_returns_403(client):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)

    response = client.get(f"/api/v1/groups/{group_id}/members")
    assert response.status_code == 403


def test_get_group_members_empty_list_for_group_with_no_members(client, authenticate_as):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)

    authenticate_as(creator_id)
    response = client.get(f"/api/v1/groups/{group_id}/members")
    assert response.status_code == 200
    assert response.json() == []


def test_get_group_members_unknown_group_returns_404(client):
    response = client.get("/api/v1/groups/unknown-group/members")
    assert response.status_code == 404
```

- [ ] **Step 4: `tests/integration/test_tasks_api.py` — replace the file**

```python
def _create_user(client, first_name="Ada", last_name="Lovelace"):
    return client.post(
        "/api/v1/users", json={"firstName": first_name, "lastName": last_name}
    ).json()["userId"]


def test_create_and_fetch_task(client, authenticate_as):
    user_id = _create_user(client)
    create_response = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": user_id}
    )
    assert create_response.status_code == 201
    body = create_response.json()
    assert body["taskState"] == "TODO"
    task_id = body["taskId"]

    authenticate_as(user_id)
    fetch_response = client.get(f"/api/v1/tasks/{task_id}")
    assert fetch_response.status_code == 200
    assert fetch_response.json()["taskId"] == task_id


def test_create_task_unknown_user_returns_404(client):
    response = client.post("/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": "unknown"})
    assert response.status_code == 404


def test_get_task_wrong_caller_returns_403(client):
    user_id = _create_user(client)
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": user_id}
    ).json()["taskId"]

    response = client.get(f"/api/v1/tasks/{task_id}")
    assert response.status_code == 403


def test_update_task_meta(client, authenticate_as):
    user_id = _create_user(client)
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": user_id}
    ).json()["taskId"]

    authenticate_as(user_id)
    response = client.patch(
        f"/api/v1/tasks/{task_id}", json={"updatedBy": user_id, "taskTitle": "Buy oat milk"}
    )
    assert response.status_code == 200
    assert response.json()["taskTitle"] == "Buy oat milk"


def test_update_task_meta_non_creator_returns_403(client):
    user_id = _create_user(client)
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": user_id}
    ).json()["taskId"]

    response = client.patch(
        f"/api/v1/tasks/{task_id}", json={"updatedBy": user_id, "taskTitle": "Buy oat milk"}
    )
    assert response.status_code == 403


def test_update_task_state(client, authenticate_as):
    user_id = _create_user(client)
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": user_id}
    ).json()["taskId"]

    authenticate_as(user_id)
    response = client.patch(
        f"/api/v1/tasks/{task_id}/state", json={"updatedBy": user_id, "taskState": "IN-PROGRESS"}
    )
    assert response.status_code == 200
    assert response.json()["taskState"] == "IN-PROGRESS"


def test_update_task_state_already_completed_returns_400(client, authenticate_as):
    user_id = _create_user(client)
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": user_id}
    ).json()["taskId"]
    authenticate_as(user_id)
    client.patch(f"/api/v1/tasks/{task_id}/state", json={"updatedBy": user_id, "taskState": "COMPLETED"})

    response = client.patch(
        f"/api/v1/tasks/{task_id}/state", json={"updatedBy": user_id, "taskState": "COMPLETED"}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["errorCode"] == "ERR_TASKS_002"


def test_update_task_state_allows_moving_out_of_completed(client, authenticate_as):
    user_id = _create_user(client)
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": user_id}
    ).json()["taskId"]
    authenticate_as(user_id)
    client.patch(f"/api/v1/tasks/{task_id}/state", json={"updatedBy": user_id, "taskState": "COMPLETED"})

    response = client.patch(
        f"/api/v1/tasks/{task_id}/state", json={"updatedBy": user_id, "taskState": "TODO"}
    )
    assert response.status_code == 200
    assert response.json()["taskState"] == "TODO"


def test_update_task_due_date(client, authenticate_as):
    user_id = _create_user(client)
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": user_id}
    ).json()["taskId"]

    authenticate_as(user_id)
    response = client.patch(
        f"/api/v1/tasks/{task_id}/due-date",
        json={"updatedBy": user_id, "taskDueDate": "2026-08-01T00:00:00Z"},
    )
    assert response.status_code == 200
    assert response.json()["taskDueDate"].startswith("2026-08-01")


def test_update_task_due_date_to_null_clears_it(client, authenticate_as):
    user_id = _create_user(client)
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": user_id}
    ).json()["taskId"]
    authenticate_as(user_id)
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


def test_update_task_state_same_state_returns_400(client, authenticate_as):
    user_id = _create_user(client)
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": user_id}
    ).json()["taskId"]

    authenticate_as(user_id)
    response = client.patch(
        f"/api/v1/tasks/{task_id}/state", json={"updatedBy": user_id, "taskState": "TODO"}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["errorCode"] == "ERR_TASKS_002"


def test_list_my_tasks_returns_created_and_assigned(client, authenticate_as):
    owner_id = _create_user(client)
    other_id = _create_user(client, first_name="Bob", last_name="Smith")
    authenticate_as(owner_id)
    my_task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "My task", "createdBy": owner_id}
    ).json()["taskId"]
    client.post("/api/v1/tasks", json={"taskTitle": "Not mine", "createdBy": other_id})

    response = client.get("/api/v1/tasks")
    assert response.status_code == 200
    task_ids = [t["taskId"] for t in response.json()]
    assert my_task_id in task_ids
```

- [ ] **Step 5: `tests/integration/test_task_group_api.py` — replace the file**

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


def test_assign_task_to_group_member(client, authenticate_as):
    creator_id = _create_user(client)
    member_id = _create_user(client, first_name="Bob", last_name="Smith")
    group_id = _create_group(client, creator_id)
    task_id = _create_task(client, creator_id)
    authenticate_as(creator_id)
    _associate_user(client, group_id, member_id)

    response = client.post(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": member_id}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["taskId"] == task_id
    assert body["groupId"] == group_id
    assert body["assigneeId"] == member_id


def test_assign_task_wrong_caller_returns_403(client, authenticate_as):
    creator_id = _create_user(client)
    member_id = _create_user(client, first_name="Bob", last_name="Smith")
    group_id = _create_group(client, creator_id)
    task_id = _create_task(client, creator_id)
    authenticate_as(creator_id)
    _associate_user(client, group_id, member_id)

    authenticate_as(member_id)
    response = client.post(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": member_id}
    )
    assert response.status_code == 403


def test_assign_task_unknown_assignee_returns_404(client):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)
    task_id = _create_task(client, creator_id)

    response = client.post(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": "unknown"}
    )
    assert response.status_code == 404


def test_assign_task_to_non_member_returns_400(client, authenticate_as):
    creator_id = _create_user(client)
    outsider_id = _create_user(client, first_name="Cara", last_name="Jones")
    group_id = _create_group(client, creator_id)
    task_id = _create_task(client, creator_id)

    authenticate_as(creator_id)
    response = client.post(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": outsider_id}
    )
    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["errorCode"] == "ERR_TASKS_001"


def test_unassign_task(client, authenticate_as):
    creator_id = _create_user(client)
    member_id = _create_user(client, first_name="Bob", last_name="Smith")
    group_id = _create_group(client, creator_id)
    task_id = _create_task(client, creator_id)
    authenticate_as(creator_id)
    _associate_user(client, group_id, member_id)
    client.post(f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": member_id})

    response = client.delete(f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee/{member_id}")
    assert response.status_code == 200
    assert response.json()["assigneeId"] is None


def test_unassign_task_wrong_caller_returns_403(client, authenticate_as):
    creator_id = _create_user(client)
    member_id = _create_user(client, first_name="Bob", last_name="Smith")
    group_id = _create_group(client, creator_id)
    task_id = _create_task(client, creator_id)
    authenticate_as(creator_id)
    _associate_user(client, group_id, member_id)
    client.post(f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": member_id})

    authenticate_as(member_id)
    response = client.delete(f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee/{member_id}")
    assert response.status_code == 403


def test_unassign_task_without_prior_assignment_returns_404(client, authenticate_as):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)
    task_id = _create_task(client, creator_id)

    authenticate_as(creator_id)
    response = client.delete(f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee/{creator_id}")
    assert response.status_code == 404


def test_unassign_task_with_mismatched_assignee_returns_404(client, authenticate_as):
    creator_id = _create_user(client)
    member_id = _create_user(client, first_name="Bob", last_name="Smith")
    other_user_id = _create_user(client, first_name="Cara", last_name="Jones")
    group_id = _create_group(client, creator_id)
    task_id = _create_task(client, creator_id)
    authenticate_as(creator_id)
    _associate_user(client, group_id, member_id)
    client.post(f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": member_id})

    response = client.delete(f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee/{other_user_id}")
    assert response.status_code == 404


def test_assign_task_to_creator_returns_400(client, authenticate_as):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)
    task_id = _create_task(client, creator_id)

    authenticate_as(creator_id)
    response = client.post(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": creator_id}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["errorCode"] == "ERR_TASKS_005"
```

- [ ] **Step 6: `tests/integration/test_full_lifecycle_api.py` — add one `authenticate_as` call**

Change:
```python
def test_full_cross_entity_lifecycle(client):
    # 1. Create the owner user.
    owner_id = _create_user(client, first_name="Ada", last_name="Lovelace")

    # 2. Create the member/assignee user.
    member_id = _create_user(client, first_name="Bob", last_name="Smith")

    # 3. Create a group with the owner as creator.
    group_id = _create_group(client, owner_id)

    # 4. Associate the member to the group.
```
to:
```python
def test_full_cross_entity_lifecycle(client, authenticate_as):
    # 1. Create the owner user.
    owner_id = _create_user(client, first_name="Ada", last_name="Lovelace")

    # 2. Create the member/assignee user.
    member_id = _create_user(client, first_name="Bob", last_name="Smith")

    # 3. Create a group with the owner as creator.
    group_id = _create_group(client, owner_id)

    # Authenticate as the owner for every subsequent ownership-gated call in
    # this lifecycle (disassociate at the end also allows the creator, so no
    # further identity switch is needed).
    authenticate_as(owner_id)

    # 4. Associate the member to the group.
```
(No other lines in this file change — every subsequent request in the test is already performed by `owner_id`'s authority under the rules implemented above.)

- [ ] **Step 7: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: PASS — every test across `tests/unit`, `tests/repositories`, `tests/integration`.

- [ ] **Step 8: Commit**

```bash
git add tests/integration/
git commit -m "test: add authenticate_as calls and new ownership/403 tests across all integration suites"
```

---

## Task 10: Documentation

**Files:**
- Modify: `OpenPoints.md`

- [ ] **Step 1: Update the "Auth & authorization" section**

Change:
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
```
to:
```markdown
## Auth & authorization
- Authentication AND ownership authorization now exist on every endpoint
  except `POST /api/v1/users` and `POST /api/v1/groups`/`POST /api/v1/tasks`
  (creation endpoints — nothing to own yet, though auth is still required).
  `current_user_id: str = Depends(verify_firebase_token)` is an explicit
  function argument on every route (moved off the old router-level
  `dependencies=[...]` wiring), threaded into the service layer, which
  raises `app.exceptions.ForbiddenError` (→ HTTP 403) when the rule fails:
  - Users: caller must be the `userId` in the path.
  - Groups (read): caller must be the creator or a member. Groups
    (write): creator only. `GET /api/v1/users/{userId}/groups`: caller
    must be that `userId`.
  - Group membership (read/associate): caller must be the creator or a
    member. Disassociate: caller must be the member being removed, OR
    the group's creator.
  - Tasks (read/state/due-date): caller must be the creator or the
    assignee. Task meta update: creator only. Assign/unassign: creator
    only.
  - New `GET /api/v1/tasks`: returns tasks created by or assigned to the
    caller, sorted by most recently updated/created first.
- The Firebase `uid` has NO mapping to this app's own `User.userId`.
  These are two different, unrelated ID spaces: `User.userId` is a
  server-generated UUID4 created by `UserService.create_user` with no
  link back to Firebase identity. A future iteration would need an
  explicit `User.firebaseUid` column (or equivalent lookup) to bridge the
  two for this authorization to be meaningful in production — today it's
  enforced but the two ID spaces don't actually correspond to anything at
  signup time.
```

- [ ] **Step 2: Run the full suite once more**

Run: `.venv/bin/pytest -v` — expect PASS.

- [ ] **Step 3: Commit**

```bash
git add OpenPoints.md
git commit -m "docs: describe the new ownership authorization rules"
```

---

## Self-Review

**Spec coverage:** every one of `ASK.md`'s per-endpoint rules maps to a specific service-method check (Tasks 2-6) and a specific router wiring change (Task 8); the new "my tasks" endpoint is `TaskService.get_tasks_for_user` + `GET /api/v1/tasks` (Task 5/8); "move to a function argument" is the router-wide refactor in Task 8.

**Placeholder scan:** every step has literal code, exact diffs, or exact commands with expected output.

**Type consistency:** every gated method's new parameter is spelled `current_user_id: Optional[str] = None` identically across all 5 services; `GroupService`'s and `TaskService`'s new 3-arg constructors are used identically in `app/dependencies.py`, `tests/conftest.py`, and every unit-test fixture that builds them (Tasks 3-7).
