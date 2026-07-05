from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import verify_firebase_token
from app.dependencies import get_task_service
from app.exceptions import BadRequestError, ForbiddenError, NotFoundError
from app.models.task import Task
from app.schemas.errors import BadRequestResponse, ErrorDetail
from app.schemas.task import (
    TaskCreateRequest,
    TaskDueDateUpdateRequest,
    TaskMetaUpdateRequest,
    TaskResponse,
    TaskStateUpdateRequest,
)
from app.services.task_service import TaskService

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


def _to_response(task: Task) -> TaskResponse:
    return TaskResponse(**task.model_dump())


@router.post(
    "",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"description": "Task creator (user) or groupId not found"},
        403: {"description": "Not authorized to create a task in that group"},
    },
)
def create_task(
    payload: TaskCreateRequest,
    current_user_id: str = Depends(verify_firebase_token),
    service: TaskService = Depends(get_task_service),
) -> TaskResponse:
    try:
        task = service.create_task(
            task_title=payload.taskTitle,
            created_by=current_user_id,
            task_desc=payload.taskDesc,
            task_due_date=payload.taskDueDate,
            group_id=payload.groupId,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return _to_response(task)


@router.get("", response_model=list[TaskResponse])
def list_my_tasks(
    current_user_id: str = Depends(verify_firebase_token),
    service: TaskService = Depends(get_task_service),
) -> list[TaskResponse]:
    tasks = service.get_tasks_for_user(current_user_id)
    return [_to_response(t) for t in tasks]


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    responses={404: {"description": "Task not found"}, 403: {"description": "Not authorized"}},
)
def get_task(
    task_id: str,
    current_user_id: str = Depends(verify_firebase_token),
    service: TaskService = Depends(get_task_service),
) -> TaskResponse:
    try:
        task = service.get_task(task_id, current_user_id=current_user_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return _to_response(task)


@router.patch(
    "/{task_id}",
    response_model=TaskResponse,
    responses={
        404: {"description": "Task or updating user not found"},
        403: {"description": "Not authorized"},
    },
)
def update_task_meta(
    task_id: str,
    payload: TaskMetaUpdateRequest,
    current_user_id: str = Depends(verify_firebase_token),
    service: TaskService = Depends(get_task_service),
) -> TaskResponse:
    try:
        task = service.update_task_meta(
            task_id,
            current_user_id=current_user_id,
            task_title=payload.taskTitle,
            task_desc=payload.taskDesc,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return _to_response(task)


@router.patch(
    "/{task_id}/state",
    response_model=TaskResponse,
    responses={
        404: {"description": "Task or updating user not found"},
        400: {
            "model": BadRequestResponse,
            "description": "Task is already COMPLETED and cannot be marked COMPLETED again",
        },
        403: {"description": "Not authorized"},
    },
)
def update_task_state(
    task_id: str,
    payload: TaskStateUpdateRequest,
    current_user_id: str = Depends(verify_firebase_token),
    service: TaskService = Depends(get_task_service),
) -> TaskResponse:
    try:
        task = service.update_task_state(
            task_id,
            current_user_id=current_user_id,
            new_state=payload.taskState,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BadRequestError as exc:
        raise HTTPException(
            status_code=exc.http_code,
            detail=ErrorDetail(errorCode=exc.error_code, message=exc.message).model_dump(),
        ) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return _to_response(task)


@router.patch(
    "/{task_id}/due-date",
    response_model=TaskResponse,
    responses={
        404: {"description": "Task or updating user not found"},
        403: {"description": "Not authorized"},
    },
)
def update_due_date(
    task_id: str,
    payload: TaskDueDateUpdateRequest,
    current_user_id: str = Depends(verify_firebase_token),
    service: TaskService = Depends(get_task_service),
) -> TaskResponse:
    try:
        task = service.update_due_date(
            task_id,
            current_user_id=current_user_id,
            due_date=payload.taskDueDate,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return _to_response(task)
