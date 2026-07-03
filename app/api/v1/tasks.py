from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_task_service
from app.exceptions import BadRequestError, NotFoundError
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
    responses={404: {"description": "Task creator (user) not found"}},
)
def create_task(
    payload: TaskCreateRequest, service: TaskService = Depends(get_task_service)
) -> TaskResponse:
    try:
        task = service.create_task(
            task_title=payload.taskTitle,
            created_by=payload.createdBy,
            task_desc=payload.taskDesc,
            task_due_date=payload.taskDueDate,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_response(task)


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    responses={404: {"description": "Task not found"}},
)
def get_task(task_id: str, service: TaskService = Depends(get_task_service)) -> TaskResponse:
    try:
        task = service.get_task(task_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_response(task)


@router.patch(
    "/{task_id}",
    response_model=TaskResponse,
    responses={404: {"description": "Task or updating user not found"}},
)
def update_task_meta(
    task_id: str, payload: TaskMetaUpdateRequest, service: TaskService = Depends(get_task_service)
) -> TaskResponse:
    try:
        task = service.update_task_meta(
            task_id,
            updated_by=payload.updatedBy,
            task_title=payload.taskTitle,
            task_desc=payload.taskDesc,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
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
    },
)
def update_task_state(
    task_id: str, payload: TaskStateUpdateRequest, service: TaskService = Depends(get_task_service)
) -> TaskResponse:
    try:
        task = service.update_task_state(task_id, updated_by=payload.updatedBy, new_state=payload.taskState)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BadRequestError as exc:
        raise HTTPException(
            status_code=exc.http_code,
            detail=ErrorDetail(errorCode=exc.error_code, message=exc.message).model_dump(),
        ) from exc
    return _to_response(task)


@router.patch(
    "/{task_id}/due-date",
    response_model=TaskResponse,
    responses={404: {"description": "Task or updating user not found"}},
)
def update_due_date(
    task_id: str, payload: TaskDueDateUpdateRequest, service: TaskService = Depends(get_task_service)
) -> TaskResponse:
    try:
        task = service.update_due_date(task_id, updated_by=payload.updatedBy, due_date=payload.taskDueDate)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_response(task)
