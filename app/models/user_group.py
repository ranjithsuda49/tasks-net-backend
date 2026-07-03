from pydantic import BaseModel


class UserGroupRelationship(BaseModel):
    uuid: str
    groupId: str
    userId: str
    relationship: str
