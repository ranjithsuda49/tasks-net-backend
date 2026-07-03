from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.enums import GroupStatus


class GroupCreateRequest(BaseModel):
    groupName: str
    groupDesc: Optional[str] = None
    groupCategory: str
    groupCreaterId: str
    groupIconUrl: Optional[str] = None


class GroupUpdateRequest(BaseModel):
    groupName: Optional[str] = None
    groupDesc: Optional[str] = None
    groupIconUrl: Optional[str] = None


class GroupStatusUpdateRequest(BaseModel):
    groupStatus: GroupStatus


class GroupResponse(BaseModel):
    groupId: str
    groupName: str
    groupDesc: Optional[str] = None
    groupCategory: str
    groupStatus: GroupStatus
    groupIconUrl: Optional[str] = None
    groupCreaterId: str
    createdAt: datetime
    updatedAt: Optional[datetime] = None
