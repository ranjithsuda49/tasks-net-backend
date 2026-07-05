import uuid
from datetime import datetime, timezone
from typing import Optional

from app.exceptions import BadRequestError, ErrorCode, ForbiddenError, NotFoundError
from app.models.enums import TaskState
from app.models.task import Task
from app.models.task_group import TaskGroupRelationship
from app.repositories.base import BaseRepository
from app.repositories.task_group_repository import TaskGroupRepository
from app.services.group_service import GroupService
from app.services.user_service import UserService


class TaskService:
    def __init__(
        self,
        repository: BaseRepository[Task],
        user_service: UserService,
        task_group_repository: TaskGroupRepository,
        group_service: GroupService,
    ):
        self._repository = repository
        self._user_service = user_service
        self._task_group_repository = task_group_repository
        self._group_service = group_service

    def create_task(
        self,
        task_title: str,
        created_by: str,
        task_desc: Optional[str] = None,
        task_due_date: Optional[datetime] = None,
        group_id: Optional[str] = None,
    ) -> Task:
        self._user_service.get_user(created_by)
        if group_id is not None:
            # Raises NotFoundError if the group doesn't exist, ForbiddenError
            # if created_by is neither the group's creator nor a member.
            self._group_service.get_group(group_id, current_user_id=created_by)
        now = datetime.now(timezone.utc)
        task = Task(
            taskId=str(uuid.uuid4()),
            taskTitle=task_title,
            taskDesc=task_desc,
            taskDueDate=task_due_date,
            taskState=TaskState.TODO,
            createdAt=now,
            createdBy=created_by,
            updatedAt=None,
            updatedBy=None,
            groupId=group_id,
        )
        created = self._repository.add(task)
        if group_id is not None:
            # Auto-bootstrap the task-group assignment with assignee = creator.
            # Inserted directly (bypassing TaskGroupService.assign()) because a
            # group's own creator can never be a UserGroupRelationship member
            # row, which would otherwise fail assign()'s is_member check even
            # though the creator is a legitimate task creator here.
            relationship = TaskGroupRelationship(
                uuid=str(uuid.uuid4()),
                taskId=created.taskId,
                groupId=group_id,
                assigneeId=created_by,
            )
            self._task_group_repository.add(relationship)
        return created

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
        current_user_id: str,
        task_title: Optional[str] = None,
        task_desc: Optional[str] = None,
    ) -> Task:
        task = self.get_task(task_id)
        if current_user_id != task.createdBy:
            raise ForbiddenError(f"User {current_user_id} is not authorized to update task {task_id}")
        updated = task.model_copy(
            update={
                "taskTitle": task_title if task_title is not None else task.taskTitle,
                "taskDesc": task_desc if task_desc is not None else task.taskDesc,
                "updatedBy": current_user_id,
                "updatedAt": datetime.now(timezone.utc),
            }
        )
        return self._repository.update(updated)

    def update_task_state(self, task_id: str, current_user_id: str, new_state: TaskState) -> Task:
        task = self.get_task(task_id, current_user_id=current_user_id)
        if task.taskState == new_state:
            raise BadRequestError(ErrorCode.TASK_ALREADY_IN_REQUESTED_STATE)
        updated = task.model_copy(
            update={
                "taskState": new_state,
                "updatedBy": current_user_id,
                "updatedAt": datetime.now(timezone.utc),
            }
        )
        return self._repository.update(updated)

    def update_due_date(
        self, task_id: str, current_user_id: str, due_date: Optional[datetime]
    ) -> Task:
        task = self.get_task(task_id, current_user_id=current_user_id)
        updated = task.model_copy(
            update={
                "taskDueDate": due_date,
                "updatedBy": current_user_id,
                "updatedAt": datetime.now(timezone.utc),
            }
        )
        return self._repository.update(updated)

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

    def list_tasks_by_group(self, group_id: str) -> list[Task]:
        return self._repository.list_by_group(group_id)
