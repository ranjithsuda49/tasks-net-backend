from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.enums import UserStatus


class Name(BaseModel):
    firstName: str
    lastName: str


class User(BaseModel):
    userId: str
    name: Name
    phoneNum: Optional[str] = None
    emailId: Optional[str] = None
    userStatus: UserStatus = UserStatus.ACTIVE
    createdAt: datetime
    updatedAt: Optional[datetime] = None
