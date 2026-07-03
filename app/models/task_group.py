from typing import Optional

from pydantic import BaseModel


class TaskGroupRelationship(BaseModel):
    uuid: str
    taskId: str
    groupId: str
    assigneeId: Optional[str] = None
