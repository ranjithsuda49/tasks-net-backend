from abc import ABC, abstractmethod
from typing import Generic, Optional, TypeVar

T = TypeVar("T")


class BaseRepository(ABC, Generic[T]):
    @abstractmethod
    def add(self, entity: T) -> T:
        ...

    @abstractmethod
    def get(self, entity_id: str) -> Optional[T]:
        ...

    @abstractmethod
    def update(self, entity: T) -> T:
        ...

    @abstractmethod
    def list_all(self) -> list[T]:
        ...
