from pydantic import BaseModel


class UserGroupAssociateRequest(BaseModel):
    userId: str
    relationship: str


class UserGroupResponse(BaseModel):
    uuid: str
    groupId: str
    userId: str
    relationship: str
