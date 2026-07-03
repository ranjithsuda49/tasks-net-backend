from typing import Optional

from app.models.group import Group
from app.repositories.base import BaseRepository


class InMemoryGroupRepository(BaseRepository[Group]):
    def __init__(self) -> None:
        self._store: dict[str, Group] = {}

    def add(self, entity: Group) -> Group:
        self._store[entity.groupId] = entity
        return entity

    def get(self, entity_id: str) -> Optional[Group]:
        return self._store.get(entity_id)

    def update(self, entity: Group) -> Group:
        self._store[entity.groupId] = entity
        return entity

    def list_all(self) -> list[Group]:
        return list(self._store.values())

    def list_by_creator(self, creater_id: str) -> list[Group]:
        return [group for group in self._store.values() if group.groupCreaterId == creater_id]
