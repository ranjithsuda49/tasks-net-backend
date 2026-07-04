import uuid
from datetime import datetime, timezone
from typing import Optional

from app.exceptions import BadRequestError, ErrorCode, NotFoundError
from app.models.enums import TaskState
from app.models.task import Task
from app.repositories.base import BaseRepository
from app.services.user_service import UserService


class TaskService:
    def __init__(self, repository: BaseRepository[Task], user_service: UserService):
        self._repository = repository
        self._user_service = user_service

    def create_task(
        self,
        task_title: str,
        created_by: str,
        task_desc: Optional[str] = None,
        task_due_date: Optional[datetime] = None,
    ) -> Task:
        self._user_service.get_user(created_by)
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
        )
        return self._repository.add(task)

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
        updated = task.model_copy(
            update={
                "taskTitle": task_title if task_title is not None else task.taskTitle,
                "taskDesc": task_desc if task_desc is not None else task.taskDesc,
                "updatedBy": updated_by,
                "updatedAt": datetime.now(timezone.utc),
            }
        )
        return self._repository.update(updated)

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

    def update_due_date(self, task_id: str, updated_by: str, due_date: Optional[datetime]) -> Task:
        self._user_service.get_user(updated_by)
        task = self.get_task(task_id)
        updated = task.model_copy(
            update={
                "taskDueDate": due_date,
                "updatedBy": updated_by,
                "updatedAt": datetime.now(timezone.utc),
            }
        )
        return self._repository.update(updated)
