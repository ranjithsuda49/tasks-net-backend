from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import verify_firebase_token
from app.dependencies import get_group_service
from app.exceptions import NotFoundError
from app.models.group import Group
from app.schemas.group import (
    GroupCreateRequest,
    GroupResponse,
    GroupStatusUpdateRequest,
    GroupUpdateRequest,
)
from app.services.group_service import GroupService

router = APIRouter(
    prefix="/api/v1", tags=["groups"], dependencies=[Depends(verify_firebase_token)]
)


def _to_response(group: Group) -> GroupResponse:
    return GroupResponse(
        groupId=group.groupId,
        groupName=group.groupName,
        groupDesc=group.groupDesc,
        groupCategory=group.groupCategory,
        groupStatus=group.groupStatus,
        groupIconUrl=group.groupIconUrl,
        groupCreaterId=group.groupCreaterId,
        createdAt=group.createdAt,
        updatedAt=group.updatedAt,
    )


@router.post(
    "/groups",
    response_model=GroupResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"description": "Group creator (user) not found"}},
)
def create_group(
    payload: GroupCreateRequest, service: GroupService = Depends(get_group_service)
) -> GroupResponse:
    try:
        group = service.create_group(
            group_name=payload.groupName,
            group_desc=payload.groupDesc,
            group_category=payload.groupCategory,
            creater_id=payload.groupCreaterId,
            group_icon_url=payload.groupIconUrl,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_response(group)


@router.get(
    "/groups/{group_id}",
    response_model=GroupResponse,
    responses={404: {"description": "Group not found"}},
)
def get_group(group_id: str, service: GroupService = Depends(get_group_service)) -> GroupResponse:
    try:
        group = service.get_group(group_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_response(group)


@router.get("/users/{user_id}/groups", response_model=list[GroupResponse])
def get_groups_by_creator(
    user_id: str, service: GroupService = Depends(get_group_service)
) -> list[GroupResponse]:
    groups = service.get_groups_by_creator(user_id)
    return [_to_response(group) for group in groups]


@router.patch(
    "/groups/{group_id}",
    response_model=GroupResponse,
    responses={404: {"description": "Group not found"}},
)
def update_group(
    group_id: str, payload: GroupUpdateRequest, service: GroupService = Depends(get_group_service)
) -> GroupResponse:
    try:
        group = service.update_group(
            group_id,
            group_name=payload.groupName,
            group_desc=payload.groupDesc,
            group_icon_url=payload.groupIconUrl,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_response(group)


@router.patch(
    "/groups/{group_id}/status",
    response_model=GroupResponse,
    responses={404: {"description": "Group not found"}},
)
def update_group_status(
    group_id: str,
    payload: GroupStatusUpdateRequest,
    service: GroupService = Depends(get_group_service),
) -> GroupResponse:
    try:
        group = service.set_status(group_id, payload.groupStatus)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_response(group)
