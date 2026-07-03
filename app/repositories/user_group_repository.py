from typing import Optional

from app.models.user_group import UserGroupRelationship
from app.repositories.base import BaseRepository


class InMemoryUserGroupRepository(BaseRepository[UserGroupRelationship]):
    def __init__(self) -> None:
        self._store: dict[str, UserGroupRelationship] = {}

    def add(self, entity: UserGroupRelationship) -> UserGroupRelationship:
        self._store[entity.uuid] = entity
        return entity

    def get(self, entity_id: str) -> Optional[UserGroupRelationship]:
        return self._store.get(entity_id)

    def update(self, entity: UserGroupRelationship) -> UserGroupRelationship:
        self._store[entity.uuid] = entity
        return entity

    def list_all(self) -> list[UserGroupRelationship]:
        return list(self._store.values())

    def find_by_user_and_group(
        self, user_id: str, group_id: str
    ) -> Optional[UserGroupRelationship]:
        for relationship in self._store.values():
            if relationship.userId == user_id and relationship.groupId == group_id:
                return relationship
        return None

    def delete(self, entity_id: str) -> None:
        self._store.pop(entity_id, None)

    def list_by_group(self, group_id: str) -> list[UserGroupRelationship]:
        return [r for r in self._store.values() if r.groupId == group_id]
