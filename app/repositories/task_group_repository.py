from typing import Optional

from app.models.task_group import TaskGroupRelationship
from app.repositories.base import BaseRepository


class InMemoryTaskGroupRepository(BaseRepository[TaskGroupRelationship]):
    def __init__(self) -> None:
        self._store: dict[str, TaskGroupRelationship] = {}

    def add(self, entity: TaskGroupRelationship) -> TaskGroupRelationship:
        self._store[entity.uuid] = entity
        return entity

    def get(self, entity_id: str) -> Optional[TaskGroupRelationship]:
        return self._store.get(entity_id)

    def update(self, entity: TaskGroupRelationship) -> TaskGroupRelationship:
        self._store[entity.uuid] = entity
        return entity

    def list_all(self) -> list[TaskGroupRelationship]:
        return list(self._store.values())

    def find_by_task_and_group(
        self, task_id: str, group_id: str
    ) -> Optional[TaskGroupRelationship]:
        for relationship in self._store.values():
            if relationship.taskId == task_id and relationship.groupId == group_id:
                return relationship
        return None
