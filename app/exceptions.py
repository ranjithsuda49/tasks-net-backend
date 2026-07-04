class NotFoundError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ForbiddenError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ConflictError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ErrorCode:
    ASSIGNEE_NOT_GROUP_MEMBER = "ERR_TASKS_001"
    TASK_ALREADY_IN_REQUESTED_STATE = "ERR_TASKS_002"
    DUPLICATE_GROUP_MEMBERSHIP = "ERR_TASKS_003"
    TASK_CREATOR_CANNOT_BE_ASSIGNEE = "ERR_TASKS_005"
    GROUP_CREATOR_CANNOT_BE_MEMBER = "ERR_TASKS_006"


ERROR_CODE_MESSAGES: dict[str, str] = {
    ErrorCode.ASSIGNEE_NOT_GROUP_MEMBER: "Assignee is not a member of the target group",
    ErrorCode.TASK_ALREADY_IN_REQUESTED_STATE: "Task is already in the requested state",
    ErrorCode.DUPLICATE_GROUP_MEMBERSHIP: "User is already associated with this group",
    ErrorCode.TASK_CREATOR_CANNOT_BE_ASSIGNEE: "Task creator cannot be assigned to their own task",
    ErrorCode.GROUP_CREATOR_CANNOT_BE_MEMBER: "Group creator cannot be a member of their own group",
}


class BadRequestError(Exception):
    http_code: int = 400

    def __init__(self, error_code: str, message: str | None = None):
        self.error_code = error_code
        self.message = message or ERROR_CODE_MESSAGES.get(error_code, "Bad request")
        super().__init__(self.message)
