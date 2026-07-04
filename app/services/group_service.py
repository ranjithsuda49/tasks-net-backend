import uuid
from datetime import datetime, timezone
from typing import Optional

from app.exceptions import NotFoundError
from app.models.enums import GroupStatus
from app.models.group import Group
from app.repositories.group_repository import GroupRepository
from app.services.user_service import UserService


class GroupService:
    def __init__(self, repository: GroupRepository, user_service: UserService):
        self._repository = repository
        self._user_service = user_service

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
        return self._repository.add(group)

    def get_group(self, group_id: str) -> Group:
        group = self._repository.get(group_id)
        if group is None:
            raise NotFoundError(f"Group {group_id} not found")
        return group

    def get_groups_by_creator(self, creater_id: str) -> list[Group]:
        return self._repository.list_by_creator(creater_id)

    def update_group(
        self,
        group_id: str,
        group_name: Optional[str] = None,
        group_desc: Optional[str] = None,
        group_icon_url: Optional[str] = None,
    ) -> Group:
        group = self.get_group(group_id)
        updated = group.model_copy(
            update={
                "groupName": group_name if group_name is not None else group.groupName,
                "groupDesc": group_desc if group_desc is not None else group.groupDesc,
                "groupIconUrl": group_icon_url if group_icon_url is not None else group.groupIconUrl,
                "updatedAt": datetime.now(timezone.utc),
            }
        )
        return self._repository.update(updated)

    def set_status(self, group_id: str, status: GroupStatus) -> Group:
        group = self.get_group(group_id)
        updated = group.model_copy(
            update={"groupStatus": status, "updatedAt": datetime.now(timezone.utc)}
        )
        return self._repository.update(updated)
