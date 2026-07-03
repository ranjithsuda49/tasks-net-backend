from typing import Optional

from app.models.task import Task
from app.repositories.base import BaseRepository


class InMemoryTaskRepository(BaseRepository[Task]):
    def __init__(self) -> None:
        self._store: dict[str, Task] = {}

    def add(self, entity: Task) -> Task:
        self._store[entity.taskId] = entity
        return entity

    def get(self, entity_id: str) -> Optional[Task]:
        return self._store.get(entity_id)

    def update(self, entity: Task) -> Task:
        self._store[entity.taskId] = entity
        return entity

    def list_all(self) -> list[Task]:
        return list(self._store.values())
