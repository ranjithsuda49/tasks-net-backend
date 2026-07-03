import uuid

from app.exceptions import NotFoundError
from app.models.task_group import TaskGroupRelationship
from app.repositories.task_group_repository import InMemoryTaskGroupRepository
from app.services.group_service import GroupService
from app.services.task_service import TaskService
from app.services.user_service import UserService


class TaskGroupService:
    def __init__(
        self,
        repository: InMemoryTaskGroupRepository,
        task_service: TaskService,
        group_service: GroupService,
        user_service: UserService,
    ):
        self._repository = repository
        self._task_service = task_service
        self._group_service = group_service
        self._user_service = user_service

    def assign(self, task_id: str, group_id: str, assignee_id: str) -> TaskGroupRelationship:
        self._task_service.get_task(task_id)
        self._group_service.get_group(group_id)
        self._user_service.get_user(assignee_id)

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
