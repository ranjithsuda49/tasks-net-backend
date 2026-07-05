from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.repositories.group_repository import GroupRepository
from app.repositories.task_group_repository import TaskGroupRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.user_group_repository import UserGroupRepository
from app.repositories.user_repository import UserRepository
from app.services.group_service import GroupService
from app.services.task_group_service import TaskGroupService
from app.services.task_service import TaskService
from app.services.user_group_service import UserGroupService
from app.services.user_service import UserService


def get_user_repository(session: Session = Depends(get_db_session)) -> UserRepository:
    return UserRepository(session)


def get_user_service(repository: UserRepository = Depends(get_user_repository)) -> UserService:
    return UserService(repository)


def get_group_repository(session: Session = Depends(get_db_session)) -> GroupRepository:
    return GroupRepository(session)


def get_user_group_repository(session: Session = Depends(get_db_session)) -> UserGroupRepository:
    return UserGroupRepository(session)


def get_group_service(
    repository: GroupRepository = Depends(get_group_repository),
    user_service: UserService = Depends(get_user_service),
    user_group_repository: UserGroupRepository = Depends(get_user_group_repository),
) -> GroupService:
    return GroupService(repository, user_service, user_group_repository)


def get_user_group_service(
    repository: UserGroupRepository = Depends(get_user_group_repository),
    user_service: UserService = Depends(get_user_service),
    group_service: GroupService = Depends(get_group_service),
) -> UserGroupService:
    return UserGroupService(repository, user_service, group_service)


def get_task_repository(session: Session = Depends(get_db_session)) -> TaskRepository:
    return TaskRepository(session)


def get_task_group_repository(session: Session = Depends(get_db_session)) -> TaskGroupRepository:
    return TaskGroupRepository(session)


def get_task_service(
    repository: TaskRepository = Depends(get_task_repository),
    user_service: UserService = Depends(get_user_service),
    task_group_repository: TaskGroupRepository = Depends(get_task_group_repository),
    group_service: GroupService = Depends(get_group_service),
) -> TaskService:
    return TaskService(repository, user_service, task_group_repository, group_service)


def get_task_group_service(
    repository: TaskGroupRepository = Depends(get_task_group_repository),
    task_service: TaskService = Depends(get_task_service),
    group_service: GroupService = Depends(get_group_service),
    user_service: UserService = Depends(get_user_service),
    user_group_service: UserGroupService = Depends(get_user_group_service),
) -> TaskGroupService:
    return TaskGroupService(
        repository, task_service, group_service, user_service, user_group_service
    )
