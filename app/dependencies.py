from functools import lru_cache

from app.repositories.group_repository import InMemoryGroupRepository
from app.repositories.task_repository import InMemoryTaskRepository
from app.repositories.user_group_repository import InMemoryUserGroupRepository
from app.repositories.user_repository import InMemoryUserRepository
from app.services.group_service import GroupService
from app.services.task_service import TaskService
from app.services.user_group_service import UserGroupService
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


@lru_cache
def get_user_group_repository() -> InMemoryUserGroupRepository:
    return InMemoryUserGroupRepository()


def get_user_group_service() -> UserGroupService:
    return UserGroupService(get_user_group_repository(), get_user_service(), get_group_service())


@lru_cache
def get_task_repository() -> InMemoryTaskRepository:
    return InMemoryTaskRepository()


def get_task_service() -> TaskService:
    return TaskService(get_task_repository(), get_user_service())
