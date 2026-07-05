import uuid
from datetime import datetime, timezone
from typing import Optional

from app.exceptions import NotFoundError
from app.models.enums import GroupStatus
from app.models.group import Group
from app.models.user_group import UserGroupRelationship
from app.repositories.group_repository import GroupRepository
from app.repositories.user_group_repository import UserGroupRepository
from app.services.authorization import ensure_owner, ensure_owner_or_related
from app.services.user_service import UserService


class GroupService:
    def __init__(
        self,
        repository: GroupRepository,
        user_service: UserService,
        user_group_repository: UserGroupRepository,
    ):
        self._repository = repository
        self._user_service = user_service
        self._user_group_repository = user_group_repository

    def create_group(
        self,
        group_name: str,
        group_desc: Optional[str],
        group_category: str,
        creater_id: str,
        group_icon_url: Optional[str] = None,
    ) -> Group:
        self._user_service.get_user(creater_id)
        now = datetime.now(timezone.utc)
        group = Group(
            groupId=str(uuid.uuid4()),
            groupName=group_name,
            groupDesc=group_desc,
            groupCategory=group_category,
            groupStatus=GroupStatus.ACTIVE,
            groupIconUrl=group_icon_url,
            groupCreaterId=creater_id,
            createdAt=now,
            updatedAt=None,
        )
        created = self._repository.add(group)
        # Every group's creator is automatically a SELF member. Inserted
        # directly (bypassing UserGroupService.associate()) because
        # GroupService cannot depend on UserGroupService — that would be a
        # circular import (UserGroupService already depends on GroupService).
        self._user_group_repository.add(
            UserGroupRelationship(
                uuid=str(uuid.uuid4()),
                groupId=created.groupId,
                userId=creater_id,
                relationship="SELF",
            )
        )
        return created

    def get_group(self, group_id: str, current_user_id: Optional[str] = None) -> Group:
        group = self._repository.get(group_id)
        if group is None:
            raise NotFoundError(f"Group {group_id} not found")
        ensure_owner_or_related(
            current_user_id,
            group.groupCreaterId,
            lambda: self._user_group_repository.find_by_user_and_group(
                current_user_id, group_id
            ) is not None,
            f"User {current_user_id} is not authorized to access group {group_id}",
        )
        return group

    def get_groups_by_creator(self, creater_id: str, current_user_id: Optional[str] = None) -> list[Group]:
        ensure_owner(
            current_user_id,
            creater_id,
            f"User {current_user_id} is not authorized to view groups created by {creater_id}",
        )
        return self._repository.list_by_creator(creater_id)

    def update_group(
        self,
        group_id: str,
        group_name: Optional[str] = None,
        group_desc: Optional[str] = None,
        group_icon_url: Optional[str] = None,
        current_user_id: Optional[str] = None,
    ) -> Group:
        group = self.get_group(group_id)
        ensure_owner(
            current_user_id,
            group.groupCreaterId,
            f"User {current_user_id} is not authorized to update group {group_id}",
        )
        updated = group.model_copy(
            update={
                "groupName": group_name if group_name is not None else group.groupName,
                "groupDesc": group_desc if group_desc is not None else group.groupDesc,
                "groupIconUrl": group_icon_url if group_icon_url is not None else group.groupIconUrl,
                "updatedAt": datetime.now(timezone.utc),
            }
        )
        return self._repository.update(updated)

    def set_status(self, group_id: str, status: GroupStatus, current_user_id: Optional[str] = None) -> Group:
        group = self.get_group(group_id)
        ensure_owner(
            current_user_id,
            group.groupCreaterId,
            f"User {current_user_id} is not authorized to update group {group_id}",
        )
        updated = group.model_copy(
            update={"groupStatus": status, "updatedAt": datetime.now(timezone.utc)}
        )
        return self._repository.update(updated)
