from typing import Optional

from pydantic import BaseModel


class TaskGroupAssignRequest(BaseModel):
    assigneeId: str


class TaskGroupResponse(BaseModel):
    uuid: str
    taskId: str
    groupId: str
    assigneeId: Optional[str] = None
