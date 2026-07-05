from typing import Optional

from sqlalchemy.orm import Session

from app.db.orm_models import TaskRow
from app.models.task import Task
from app.repositories.base import BaseRepository


class TaskRepository(BaseRepository[Task]):
    def __init__(self, session: Session):
        self._session = session

    def add(self, entity: Task) -> Task:
        row = TaskRow(
            id=entity.taskId,
            task_title=entity.taskTitle,
            task_desc=entity.taskDesc,
            task_due_date=entity.taskDueDate,
            task_state=entity.taskState,
            created_at=entity.createdAt,
            created_by=entity.createdBy,
            updated_at=entity.updatedAt,
            updated_by=entity.updatedBy,
            group_id=entity.groupId,
        )
        self._session.add(row)
        self._session.flush()
        return entity

    def get(self, entity_id: str) -> Optional[Task]:
        row = self._session.get(TaskRow, entity_id)
        return self._to_domain(row) if row is not None else None

    def update(self, entity: Task) -> Task:
        # group_id is never written here: Task.groupId is immutable after
        # creation, and this is where that guarantee is enforced.
        row = self._session.get(TaskRow, entity.taskId)
        row.task_title = entity.taskTitle
        row.task_desc = entity.taskDesc
        row.task_due_date = entity.taskDueDate
        row.task_state = entity.taskState
        row.updated_at = entity.updatedAt
        row.updated_by = entity.updatedBy
        self._session.flush()
        return entity

    def list_all(self) -> list[Task]:
        return [self._to_domain(row) for row in self._session.query(TaskRow).all()]

    def list_by_creator(self, created_by: str) -> list[Task]:
        rows = self._session.query(TaskRow).filter(TaskRow.created_by == created_by).all()
        return [self._to_domain(row) for row in rows]

    def list_by_group(self, group_id: str) -> list[Task]:
        rows = self._session.query(TaskRow).filter(TaskRow.group_id == group_id).all()
        return [self._to_domain(row) for row in rows]

    @staticmethod
    def _to_domain(row: TaskRow) -> Task:
        return Task(
            taskId=row.id,
            taskTitle=row.task_title,
            taskDesc=row.task_desc,
            taskDueDate=row.task_due_date,
            taskState=row.task_state,
            createdAt=row.created_at,
            createdBy=row.created_by,
            updatedAt=row.updated_at,
            updatedBy=row.updated_by,
            groupId=row.group_id,
        )
