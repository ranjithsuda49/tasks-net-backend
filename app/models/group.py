from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.enums import GroupStatus


class Group(BaseModel):
    groupId: str
    groupName: str
    groupDesc: Optional[str] = None
    groupCategory: str
    groupStatus: GroupStatus = GroupStatus.ACTIVE
    groupIconUrl: Optional[str] = None
    groupCreaterId: str
    createdAt: datetime
    updatedAt: Optional[datetime] = None
