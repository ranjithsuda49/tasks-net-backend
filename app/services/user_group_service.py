import uuid

from app.exceptions import BadRequestError, ErrorCode, NotFoundError
from app.models.user_group import UserGroupRelationship
from app.repositories.user_group_repository import InMemoryUserGroupRepository
from app.services.group_service import GroupService
from app.services.user_service import UserService


class UserGroupService:
    def __init__(
        self,
        repository: InMemoryUserGroupRepository,
        user_service: UserService,
        group_service: GroupService,
    ):
        self._repository = repository
        self._user_service = user_service
        self._group_service = group_service

    def associate(self, user_id: str, group_id: str, relationship: str) -> UserGroupRelationship:
        self._user_service.get_user(user_id)
        self._group_service.get_group(group_id)
        if self.is_member(user_id, group_id):
            raise BadRequestError(ErrorCode.DUPLICATE_GROUP_MEMBERSHIP)
        entity = UserGroupRelationship(
            uuid=str(uuid.uuid4()), groupId=group_id, userId=user_id, relationship=relationship
        )
        return self._repository.add(entity)

    def disassociate(self, user_id: str, group_id: str) -> None:
        existing = self._repository.find_by_user_and_group(user_id, group_id)
        if existing is None:
            raise NotFoundError(f"User {user_id} is not associated with group {group_id}")
        self._repository.delete(existing.uuid)

    def list_by_group(self, group_id: str) -> list[UserGroupRelationship]:
        return self._repository.list_by_group(group_id)

    def is_member(self, user_id: str, group_id: str) -> bool:
        return self._repository.find_by_user_and_group(user_id, group_id) is not None
