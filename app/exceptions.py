class NotFoundError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ConflictError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ErrorCode:
    ASSIGNEE_NOT_GROUP_MEMBER = "ERR_TASKS_001"
    TASK_ALREADY_COMPLETED = "ERR_TASKS_002"
    DUPLICATE_GROUP_MEMBERSHIP = "ERR_TASKS_003"


ERROR_CODE_MESSAGES: dict[str, str] = {
    ErrorCode.ASSIGNEE_NOT_GROUP_MEMBER: "Assignee is not a member of the target group",
    ErrorCode.TASK_ALREADY_COMPLETED: "Task is already COMPLETED and cannot be marked COMPLETED again",
    ErrorCode.DUPLICATE_GROUP_MEMBERSHIP: "User is already associated with this group",
}


class BadRequestError(Exception):
    http_code: int = 400

    def __init__(self, error_code: str, message: str | None = None):
        self.error_code = error_code
        self.message = message or ERROR_CODE_MESSAGES.get(error_code, "Bad request")
        super().__init__(self.message)
