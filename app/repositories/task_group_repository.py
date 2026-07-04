from typing import Optional

from sqlalchemy.orm import Session

from app.db.orm_models import GroupTaskRow
from app.models.task_group import TaskGroupRelationship
from app.repositories.base import BaseRepository


class TaskGroupRepository(BaseRepository[TaskGroupRelationship]):
    def __init__(self, session: Session):
        self._session = session

    def add(self, entity: TaskGroupRelationship) -> TaskGroupRelationship:
        row = GroupTaskRow(
            id=entity.uuid,
            task_id=entity.taskId,
            group_id=entity.groupId,
            assignee_id=entity.assigneeId,
        )
        self._session.add(row)
        self._session.flush()
        return entity

    def get(self, entity_id: str) -> Optional[TaskGroupRelationship]:
        row = self._session.get(GroupTaskRow, entity_id)
        return self._to_domain(row) if row is not None else None

    def update(self, entity: TaskGroupRelationship) -> TaskGroupRelationship:
        row = self._session.get(GroupTaskRow, entity.uuid)
        row.assignee_id = entity.assigneeId
        self._session.flush()
        return entity

    def list_all(self) -> list[TaskGroupRelationship]:
        return [self._to_domain(row) for row in self._session.query(GroupTaskRow).all()]

    def find_by_task_and_group(
        self, task_id: str, group_id: str
    ) -> Optional[TaskGroupRelationship]:
        row = (
            self._session.query(GroupTaskRow)
            .filter(GroupTaskRow.task_id == task_id, GroupTaskRow.group_id == group_id)
            .first()
        )
        return self._to_domain(row) if row is not None else None

    def list_by_task(self, task_id: str) -> list[TaskGroupRelationship]:
        rows = self._session.query(GroupTaskRow).filter(GroupTaskRow.task_id == task_id).all()
        return [self._to_domain(row) for row in rows]

    def list_by_assignee(self, assignee_id: str) -> list[TaskGroupRelationship]:
        rows = self._session.query(GroupTaskRow).filter(GroupTaskRow.assignee_id == assignee_id).all()
        return [self._to_domain(row) for row in rows]

    @staticmethod
    def _to_domain(row: GroupTaskRow) -> TaskGroupRelationship:
        return TaskGroupRelationship(
            uuid=row.id,
            taskId=row.task_id,
            groupId=row.group_id,
            assigneeId=row.assignee_id,
        )
