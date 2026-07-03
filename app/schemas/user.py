from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.enums import UserStatus


class NameSchema(BaseModel):
    firstName: str
    lastName: str


class UserCreateRequest(BaseModel):
    firstName: str
    lastName: str
    phoneNum: Optional[str] = None
    emailId: Optional[str] = None


class UserUpdateRequest(BaseModel):
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    phoneNum: Optional[str] = None
    emailId: Optional[str] = None


class UserStatusUpdateRequest(BaseModel):
    userStatus: UserStatus


class UserResponse(BaseModel):
    userId: str
    name: NameSchema
    phoneNum: Optional[str] = None
    emailId: Optional[str] = None
    userStatus: UserStatus
    createdAt: datetime
    updatedAt: Optional[datetime] = None
