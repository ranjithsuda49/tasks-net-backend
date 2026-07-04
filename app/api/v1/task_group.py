from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import verify_firebase_token
from app.dependencies import get_task_group_service
from app.exceptions import BadRequestError, NotFoundError
from app.schemas.errors import BadRequestResponse, ErrorDetail
from app.schemas.task_group import TaskGroupAssignRequest, TaskGroupResponse
from app.services.task_group_service import TaskGroupService

router = APIRouter(
    prefix="/api/v1/groups/{group_id}/tasks/{task_id}/assignee",
    tags=["task-group"],
    dependencies=[Depends(verify_firebase_token)],
)


@router.post(
    "",
    response_model=TaskGroupResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"description": "Task, Group, or Assignee (user) not found"},
        400: {
            "model": BadRequestResponse,
            "description": "Assignee is not a member of the target group",
        },
    },
)
def assign_task(
    group_id: str,
    task_id: str,
    payload: TaskGroupAssignRequest,
    service: TaskGroupService = Depends(get_task_group_service),
) -> TaskGroupResponse:
    try:
        relationship = service.assign(task_id, group_id, payload.assigneeId)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BadRequestError as exc:
        raise HTTPException(
            status_code=exc.http_code,
            detail=ErrorDetail(errorCode=exc.error_code, message=exc.message).model_dump(),
        ) from exc
    return TaskGroupResponse(**relationship.model_dump())


@router.delete(
    "/{assignee_id}",
    response_model=TaskGroupResponse,
    responses={404: {"description": "No matching task-group assignment found for that assignee"}},
)
def unassign_task(
    group_id: str,
    task_id: str,
    assignee_id: str,
    service: TaskGroupService = Depends(get_task_group_service),
) -> TaskGroupResponse:
    try:
        relationship = service.unassign(task_id, group_id, assignee_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return TaskGroupResponse(**relationship.model_dump())
