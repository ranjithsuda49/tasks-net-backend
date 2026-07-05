from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.enums import TaskState


class Task(BaseModel):
    taskId: str
    taskTitle: str
    taskDesc: Optional[str] = None
    taskDueDate: Optional[datetime] = None
    taskState: TaskState = TaskState.TODO
    createdAt: datetime
    createdBy: str
    updatedAt: Optional[datetime] = None
    updatedBy: Optional[str] = None
    groupId: Optional[str] = None
