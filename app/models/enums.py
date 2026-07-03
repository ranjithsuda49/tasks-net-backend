from enum import Enum


class UserStatus(str, Enum):
    ACTIVE = "ACTIVE"
    IN_ACTIVE = "IN-ACTIVE"


class GroupStatus(str, Enum):
    ACTIVE = "ACTIVE"
    IN_ACTIVE = "IN-ACTIVE"


class TaskState(str, Enum):
    TODO = "TODO"
    IN_PROGRESS = "IN-PROGRESS"
    COMPLETED = "COMPLETED"
