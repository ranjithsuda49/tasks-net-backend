from functools import lru_cache

from app.repositories.group_repository import InMemoryGroupRepository
from app.repositories.user_repository import InMemoryUserRepository
from app.services.group_service import GroupService
from app.services.user_service import UserService


@lru_cache
def get_user_repository() -> InMemoryUserRepository:
    return InMemoryUserRepository()


def get_user_service() -> UserService:
    return UserService(get_user_repository())


@lru_cache
def get_group_repository() -> InMemoryGroupRepository:
    return InMemoryGroupRepository()


def get_group_service() -> GroupService:
    return GroupService(get_group_repository(), get_user_service())
