import uuid
from typing import Optional

from app.exceptions import BadRequestError, ErrorCode, ForbiddenError, NotFoundError
from app.models.user_group import UserGroupRelationship
from app.repositories.user_group_repository import UserGroupRepository
from app.services.group_service import GroupService
from app.services.user_service import UserService


class UserGroupService:
    def __init__(
        self,
        repository: UserGroupRepository,
        user_service: UserService,
        group_service: GroupService,
    ):
        self._repository = repository
        self._user_service = user_service
        self._group_service = group_service

    def associate(
        self, user_id: str, group_id: str, relationship: str, current_user_id: Optional[str] = None
    ) -> UserGroupRelationship:
        self._user_service.get_user(user_id)
        group = self._group_service.get_group(group_id, current_user_id=current_user_id)
        if user_id == group.groupCreaterId:
            raise BadRequestError(ErrorCode.GROUP_CREATOR_CANNOT_BE_MEMBER)
        if self.is_member(user_id, group_id):
            raise BadRequestError(ErrorCode.DUPLICATE_GROUP_MEMBERSHIP)
        entity = UserGroupRelationship(
            uuid=str(uuid.uuid4()), groupId=group_id, userId=user_id, relationship=relationship
        )
        return self._repository.add(entity)

    def disassociate(self, user_id: str, group_id: str, current_user_id: Optional[str] = None) -> None:
        if current_user_id is not None and current_user_id != user_id:
            group = self._group_service.get_group(group_id)
            if current_user_id != group.groupCreaterId:
                raise ForbiddenError(
                    f"User {current_user_id} is not authorized to remove user {user_id} from group {group_id}"
                )
        existing = self._repository.find_by_user_and_group(user_id, group_id)
        if existing is None:
            raise NotFoundError(f"User {user_id} is not associated with group {group_id}")
        self._repository.delete(existing.uuid)

    def list_by_group(
        self, group_id: str, current_user_id: Optional[str] = None
    ) -> list[UserGroupRelationship]:
        self._group_service.get_group(group_id, current_user_id=current_user_id)
        return self._repository.list_by_group(group_id)

    def is_member(self, user_id: str, group_id: str) -> bool:
        return self._repository.find_by_user_and_group(user_id, group_id) is not None
