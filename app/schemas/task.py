from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.enums import TaskState


class TaskCreateRequest(BaseModel):
    taskTitle: str
    taskDesc: Optional[str] = None
    taskDueDate: Optional[datetime] = None


class TaskMetaUpdateRequest(BaseModel):
    updatedBy: str
    taskTitle: Optional[str] = None
    taskDesc: Optional[str] = None


class TaskStateUpdateRequest(BaseModel):
    updatedBy: str
    taskState: TaskState


class TaskDueDateUpdateRequest(BaseModel):
    updatedBy: str
    taskDueDate: Optional[datetime] = None


class TaskResponse(BaseModel):
    taskId: str
    taskTitle: str
    taskDesc: Optional[str] = None
    taskDueDate: Optional[datetime] = None
    taskState: TaskState
    createdAt: datetime
    createdBy: str
    updatedAt: Optional[datetime] = None
    updatedBy: Optional[str] = None
