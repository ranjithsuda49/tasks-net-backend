from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_task_group_service
from app.exceptions import NotFoundError
from app.schemas.task_group import TaskGroupAssignRequest, TaskGroupResponse
from app.services.task_group_service import TaskGroupService

router = APIRouter(prefix="/api/v1/groups/{group_id}/tasks/{task_id}/assignee", tags=["task-group"])


@router.post("", response_model=TaskGroupResponse, status_code=status.HTTP_201_CREATED)
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
    return TaskGroupResponse(**relationship.model_dump())


@router.delete("/{assignee_id}", response_model=TaskGroupResponse)
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
