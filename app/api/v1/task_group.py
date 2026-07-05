from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import verify_firebase_token
from app.dependencies import get_task_group_service
from app.exceptions import BadRequestError, ForbiddenError, NotFoundError
from app.schemas.errors import BadRequestResponse, ErrorDetail
from app.schemas.task import TaskResponse
from app.schemas.task_group import TaskGroupAssignRequest, TaskGroupResponse
from app.services.task_group_service import TaskGroupService

router = APIRouter(prefix="/api/v1/groups/{group_id}/tasks/{task_id}/assignee", tags=["task-group"])

group_tasks_router = APIRouter(prefix="/api/v1/groups/{group_id}/tasks", tags=["task-group"])


@router.patch(
    "",
    response_model=TaskGroupResponse,
    responses={
        404: {"description": "Task, Group, Assignee (user), or existing assignment not found"},
        400: {
            "model": BadRequestResponse,
            "description": "Requested assignee is same as current assignee, or not a group member",
        },
        403: {"description": "Not authorized"},
    },
)
def reassign_task(
    group_id: str,
    task_id: str,
    payload: TaskGroupAssignRequest,
    current_user_id: str = Depends(verify_firebase_token),
    service: TaskGroupService = Depends(get_task_group_service),
) -> TaskGroupResponse:
    try:
        relationship = service.reassign(
            task_id, group_id, payload.assigneeId, current_user_id=current_user_id
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
    return TaskGroupResponse(**relationship.model_dump())


@group_tasks_router.get(
    "",
    response_model=list[TaskResponse],
    responses={
        404: {"description": "Group not found"},
        403: {"description": "Not authorized"},
    },
)
def list_group_tasks(
    group_id: str,
    current_user_id: str = Depends(verify_firebase_token),
    service: TaskGroupService = Depends(get_task_group_service),
) -> list[TaskResponse]:
    try:
        tasks = service.list_tasks_for_group(group_id, current_user_id=current_user_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return [TaskResponse(**t.model_dump()) for t in tasks]
