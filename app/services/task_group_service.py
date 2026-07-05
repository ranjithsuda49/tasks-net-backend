import uuid
from typing import Optional

from app.exceptions import BadRequestError, ErrorCode, ForbiddenError, NotFoundError
from app.models.task import Task
from app.models.task_group import TaskGroupRelationship
from app.repositories.task_group_repository import TaskGroupRepository
from app.services.group_service import GroupService
from app.services.task_service import TaskService
from app.services.user_group_service import UserGroupService
from app.services.user_service import UserService


class TaskGroupService:
    def __init__(
        self,
        repository: TaskGroupRepository,
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

    def assign(
        self, task_id: str, group_id: str, assignee_id: str, current_user_id: Optional[str] = None
    ) -> TaskGroupRelationship:
        task = self._task_service.get_task(task_id)
        self._group_service.get_group(group_id)
        self._user_service.get_user(assignee_id)
        if current_user_id is not None and current_user_id != task.createdBy:
            raise ForbiddenError(f"User {current_user_id} is not authorized to assign task {task_id}")
        # A group's creator can never be a UserGroupRelationship member row
        # (GROUP_CREATOR_CANNOT_BE_MEMBER), so the membership check is
        # skipped for the task's own creator — otherwise retiring
        # ERR_TASKS_005 would be meaningless for this endpoint.
        if assignee_id != task.createdBy and not self._user_group_service.is_member(assignee_id, group_id):
            raise BadRequestError(ErrorCode.ASSIGNEE_NOT_GROUP_MEMBER)

        existing = self._repository.find_by_task_and_group(task_id, group_id)
        if existing is not None:
            updated = existing.model_copy(update={"assigneeId": assignee_id})
            return self._repository.update(updated)

        entity = TaskGroupRelationship(
            uuid=str(uuid.uuid4()), taskId=task_id, groupId=group_id, assigneeId=assignee_id
        )
        return self._repository.add(entity)

    def reassign(
        self,
        task_id: str,
        group_id: str,
        assignee_id: str,
        current_user_id: Optional[str] = None,
    ) -> TaskGroupRelationship:
        self._task_service.get_task(task_id)
        # Creator-or-member (same rule as GroupService.get_group elsewhere) —
        # deliberately not creator-only, unlike assign(). Raises NotFoundError
        # if the group doesn't exist, ForbiddenError if caller is neither.
        self._group_service.get_group(group_id, current_user_id=current_user_id)
        self._user_service.get_user(assignee_id)

        existing = self._repository.find_by_task_and_group(task_id, group_id)
        if existing is None:
            raise NotFoundError(f"No existing assignment for task {task_id} in group {group_id}")
        if assignee_id == existing.assigneeId:
            raise BadRequestError(ErrorCode.REASSIGN_ASSIGNEE_UNCHANGED)
        if not self._user_group_service.is_member(assignee_id, group_id):
            raise BadRequestError(ErrorCode.REASSIGN_ASSIGNEE_NOT_GROUP_MEMBER)

        updated = existing.model_copy(update={"assigneeId": assignee_id})
        return self._repository.update(updated)

    def list_tasks_for_group(self, group_id: str, current_user_id: Optional[str] = None) -> list[Task]:
        self._group_service.get_group(group_id, current_user_id=current_user_id)
        return self._task_service.list_tasks_by_group(group_id)
