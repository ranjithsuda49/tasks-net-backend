from functools import lru_cache

from app.repositories.user_repository import InMemoryUserRepository
from app.services.user_service import UserService


@lru_cache
def get_user_repository() -> InMemoryUserRepository:
    return InMemoryUserRepository()


def get_user_service() -> UserService:
    return UserService(get_user_repository())
