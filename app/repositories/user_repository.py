from typing import Optional

from app.models.user import User
from app.repositories.base import BaseRepository


class InMemoryUserRepository(BaseRepository[User]):
    def __init__(self) -> None:
        self._store: dict[str, User] = {}

    def add(self, entity: User) -> User:
        self._store[entity.userId] = entity
        return entity

    def get(self, entity_id: str) -> Optional[User]:
        return self._store.get(entity_id)

    def update(self, entity: User) -> User:
        self._store[entity.userId] = entity
        return entity

    def list_all(self) -> list[User]:
        return list(self._store.values())
